from django.http import JsonResponse
from django.shortcuts import render, reverse

from id_verify.models import consent_to_bgcheck_paragraph
from id_verify.verify_id_ui import (
    handle_submission_post, handle_opt_out_bgcheck)
from reservations.models.money import get_reservation_from_query
from util.channels import cc_photo_required, safe_channel
from util.email import EmailSender
from util.random_string import random_string


def verify_id(request):
  guest_first = request.GET.get('guest_first', '')
  channel = safe_channel(request.GET.get('channel', ''))
  phone = ''
  cc_required = cc_photo_required(channel)
  reservation = get_reservation_from_query(request.GET)
  background_check = False
  if reservation:
    guest_first = reservation.guest.first_name or reservation.guest.full_name
    channel = reservation.channel
    phone = reservation.guest.formatted_phone()
    cc_required = reservation.cc_photo_required()
    background_check = reservation.rental.building.background_check_guests
  random_str = random_string(7)
  context = {
      'query': str(request.GET.dict()),
      'unique_form_id': random_str,
      'guest_first': guest_first,
      'channel': channel,
      'guest_phone': phone,
      'cc_required': cc_required,
      'reservation': reservation,
      'background_check': background_check,
      'submit_url': reverse('verify_id_submit'),
      'consent_to_bgcheck_paragraph': consent_to_bgcheck_paragraph()}
  return render(request, 'verify_my_id.html', context=context)


def verify_id_submit(request):
  if request.POST.get('bgcheck_opt_out', False):
    handle_opt_out_bgcheck(request.POST)
    return JsonResponse({'redirect': reverse(confirm_bgcheck_opt_out)})
  # I still don't know how these bad email addresses got through client side
  # validation.
  if request.POST.get('submit_email', '').find('@') == -1:
    return JsonResponse({'email': 'invalid', 'problem_count': 1})
  handle_submission_post(request.POST, EmailSender())
  return JsonResponse({'redirect': reverse(thanks_for_verifying_id)})


def thanks_for_verifying_id(request):
  return render(request, 'verify_my_id_thanks.html')


def confirm_bgcheck_opt_out(request):
  return render(request, 'confirm_bgcheck_opt_out.html')
