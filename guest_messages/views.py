import json

from django.contrib.auth.decorators import login_required, permission_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from rest_framework.parsers import JSONParser

from guest_messages.forms import SMSTemplateFormSet, EmailTemplateFormSet
from guest_messages.models import (
    SMS, Email, SMSTemplate, EmailTemplate, RawMandrillEvent)
from util.fake_admin import admin_context


SIMPLE_TEMPLATE_TAGS = [
    'guest_first',
    'listing_address_city',
    'listing_address',
    'guest_email',
    'checkout_date',
    'checkout_time',
    'checkin_date',
    'checkin_time',
    'main_checkin_instructions_link',
    'main_property_access_codes_in_order_of_use',
    'master_access_code_building_door_electronic_lock',
    'master_access_code_apartment_door_electronic_lock',
    'wifi_network_name',
    'wifi_password',
    'building_trash_instructions',
    'link_to_property_page_in_helpdocs',
    'google_maps_link',
    'departure_check_list',
    'local_bag_storage_info',
    'local_bag_storage_link',
    'parking_link',
    'public_transportation_link',
    'local_recommendations_link',
    'walking_to_nearest_path_stations',
    'parking_suggestions_no_links',
    'public_transport_no_link',
    'walk_time_to_nearest_train',
    'laundry_info']


@login_required
@permission_required('guest_messages.change_smstemplate')
def edit_sms_templates(request):
  if request.method == 'POST':
    formset = SMSTemplateFormSet(request.POST)
    if formset.is_valid():
      formset.save()
      formset = SMSTemplateFormSet(queryset=SMSTemplate.objects.all())
  else:
    formset = SMSTemplateFormSet(queryset=SMSTemplate.objects.all())
  context = admin_context(
      'Guest SMS templates',
      formset=formset,
      simple_template_tags=SIMPLE_TEMPLATE_TAGS)
  return render(request, 'sms_templates.html', context=context)


@login_required
@permission_required('guest_messages.change_emailtemplate')
def edit_email_templates(request):
  if request.method == 'POST':
    formset = EmailTemplateFormSet(request.POST)
    if formset.is_valid():
      formset.save()
      formset = EmailTemplateFormSet(queryset=EmailTemplate.objects.all())
  else:
    formset = EmailTemplateFormSet(queryset=EmailTemplate.objects.all())
  context = admin_context(
      'Guest Email templates',
      formset=formset,
      simple_template_tags=SIMPLE_TEMPLATE_TAGS)
  return render(request, 'email_templates.html', context=context)


@login_required
def send_test_email(request):
  message = Email.objects.send_test(request.POST)
  return JsonResponse({'message': message})


@login_required
def send_test_sms(request):
  message = SMS.objects.send_test(request.POST)
  return JsonResponse({'message': message})


@csrf_exempt
def mandrill_webhook(request):
  # Mandrill tests your webhook with an empty post.
  if request.method == 'POST' and request.POST:
    data = JSONParser().parse(request)
    data_str = json.dumps(data)

    # Save the raw event first in case there's a problem processing it.
    # Then we can go back through and fix the problem.
    RawMandrillEvent.objects.create(json=data_str)

  return HttpResponse('Ok.')
