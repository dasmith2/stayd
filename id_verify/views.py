import os
from random import choices
from rq import Queue
import string

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, reverse

from guesty.api import GuestyAPIGetter
from id_verify.models import (
    Submission, SubmissionResizer, do_resend_id_verification)
from id_verify.s3 import S3
from reservations.models import Reservation
from util.fake_admin import admin_context
from util.email import EmailSender
from worker import conn


q = Queue(connection=conn)


def background_test(request):
  q.enqueue(delete_me_email_message, 'Test message')


def delete_me_email_message(msg):
  EmailSender().send_mail(
      'Sent from a bg thread', msg, settings.SERVER_EMAIL, ['dave@heroku.com'])


def is_verifier(function):
  def wrap(request, *args, **kwargs):
    if request.user.groups.filter(name='id_verify').exists():
      return function(request, *args, **kwargs)
    return render(request, 'bare_bones_message.html', context={
        'title': 'Permission denied',
        'message': 'You need to be a member of the id_verify group.'})
  return wrap


@login_required
@is_verifier
def submissions(request):
  if request.method == 'POST':
    Submission.objects.handle_id_verify_list_post(
        request.POST, GuestyAPIGetter())
  submissions = Submission.objects.checkable_submissions()
  context = submissions_context(0, submissions=submissions)
  return render(request, 'admin_ids_and_ccs_submissions.html', context=context)


@login_required
@is_verifier
def payment_problems(request):
  reservations = Reservation.objects.payment_problems().select_related(
      'guest', 'guestyreservation')
  context = submissions_context(1, reservations=reservations)
  return render(request, 'admin_ids_and_ccs_unpaid.html', context=context)


@login_required
@is_verifier
def no_cc_info(request):
  reservations = Reservation.objects.no_cc_info().select_related(
      'guest', 'guestyreservation')
  context = submissions_context(2, reservations=reservations)
  return render(request, 'admin_ids_and_ccs_no_cc_info.html', context=context)


def submissions_context(list_index, **kwargs):
  return admin_context(
      'IDs and Credit Cards',
      valid_selected=list_index == 0,
      unpaid_selected=list_index == 1,
      no_cc_info_selected=list_index == 2,
      valid_url=reverse('submissions'),
      unpaid_url=reverse('payment_problems'),
      no_cc_info_url=reverse('no_cc_info'),
      unpaid_count=Reservation.objects.payment_problems().count(),
      valid_count=Submission.objects.checkable_submissions().count(),
      no_cc_info_count=Reservation.objects.no_cc_info().count(),
      **kwargs)


@login_required
@is_verifier
def view_image(request, file_name):
  if not os.path.exists(file_name):  # More or less always.
    S3().download(file_name)
  f = open(file_name, "rb")
  read = f.read()
  f.close()
  os.remove(file_name)
  return HttpResponse(read, content_type="image/jpeg")


@login_required
@is_verifier
def resend_id_verification(request, reservation_id):
  return JsonResponse(do_resend_id_verification(reservation_id))


def verify_id(request):
  if request.method == 'POST':
    Submission.objects.handle_submission_post(
        request.POST, GuestyAPIGetter(), EmailSender(), SubmissionResizer())
    return redirect(reverse(thanks_for_verifying_id))
  name = request.GET.get('name', '')
  guest_first = name
  channel = ''
  reservation = None
  phone = ''
  chargebacks = True
  if name:
    reservation = Submission.objects.get_reservation_by_guest_name(name)
    if reservation:
      guest_first = reservation.guest.first_name or reservation.guest.full_name
      channel = reservation.listing.channel
      phone = reservation.guest.formatted_phone()
      chargebacks = reservation.we_assume_credit_card_risk()
  random_str = ''.join(choices(string.ascii_uppercase + string.digits, k=7))
  context = {
      'guest_name_from_query': name,
      'guest_first': guest_first,
      'channel': channel,
      'guest_phone': phone,
      'chargebacks': chargebacks,
      'id_file_prefix': 'random{}_id'.format(random_str),
      'cc_file_prefix': 'random{}_cc'.format(random_str),
      'reservation': reservation}
  return render(request, 'verify_my_id.html', context=context)


def thanks_for_verifying_id(request):
  return render(request, 'verify_my_id_thanks.html')


def sign_s3(request):
  """ The user is about to try to upload a photo directly to S3. We gotta
  sign it and say where it goes. """
  file_type = request.GET.get('file_type', '')
  destination_prefix = request.GET.get('destination_prefix', '')
  if not file_type:
    return HttpResponse(
        'You have to include a file_type parameter.', status=400)
  if not destination_prefix:
    return HttpResponse(
        'You have to include a destination_prefix parameter.', status=400)
  if file_type == 'image/jpeg':
    suffix = 'jpg'
  elif file_type == 'image/png':
    suffix = 'png'
  else:
    raise Exception(
        'Not sure what to do with file_type {}'.format(file_type))

  destination_file_name = '{}.{}'.format(destination_prefix, suffix)
  presigned_post = _get_presigned_post(destination_file_name, file_type)

  return JsonResponse({
      'presigned_post': presigned_post,
      'destination_file_name': destination_file_name})


def _get_presigned_post(file_name, file_type):
  return S3().generate_presigned_post(
      Bucket=settings.S3_BUCKET_NAME,
      Key=file_name,
      Fields={"Content-Type": file_type},
      Conditions=[{"Content-Type": file_type}],
      ExpiresIn=3600)
