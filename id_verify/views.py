import os
from random import choices
import string

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, reverse

from guesty.api import GuestyAPIGetter
from id_verify.models import Submission, SubmissionResizer
from id_verify.s3 import S3
from util.fake_admin import admin_context
from util.email import EmailSender


def is_verifier(user):
  return user.groups.filter(name='id_verify').exists()


@login_required
def id_verification_list(request):
  if not is_verifier(request.user):
    return render(request, 'bare_bones_message.html', context={
        'title': 'Permission denied',
        'message': 'You need to be a member of the id_verify group.'})
  if request.method == 'POST':
    Submission.objects.handle_id_verify_list_post(
        request.POST, GuestyAPIGetter())
  context = admin_context(
      'Stayd ID verification',
      submissions=Submission.objects.check_these())
  return render(request, 'id_verification_list.html', context=context)


@login_required
def view_image(request, file_name):
  if not os.path.exists(file_name):  # More or less always.
    S3().download(file_name)
  f = open(file_name, "rb")
  read = f.read()
  f.close()
  os.remove(file_name)
  return HttpResponse(read, content_type="image/jpeg")


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
  return render(request, 'wizard.html', context=context)


def thanks_for_verifying_id(request):
  return render(request, 'thanks_for_verify.html')


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
