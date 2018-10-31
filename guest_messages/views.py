from collections import namedtuple
from datetime import date, timedelta

from django.contrib.auth.decorators import login_required, permission_required
from django.db import connection
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from errors.models import notify
from guest_messages.forms import SMSTemplateFormSet, EmailTemplateFormSet
from guest_messages.models.models import (
    SMS, Email, SMSTemplate, EmailTemplate, RawMandrillEvent)
from util.admin import admin_context, simple_date_range_admin_page


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
  # Mandrill docs say something about verifying webhooks with a HEAD request.
  if request.method == 'POST':
    RawMandrillEvent.objects.handle_webhook(request.POST)
  return HttpResponse('Ok.')


def message_delays(request, from_date_str='', to_date_str=''):
  """
  SELECT SUM(when_did - when_should) / COUNT(1) AS avg_delay,
  date_trunc('day', when_should) AS day
  FROM guest_messages_sms
  WHERE when_should >= '2018-10-01'
  AND when_should < '2018-11-01'
  GROUP BY day ORDER BY day;

  SELECT COUNT(1), EXTRACT(minute FROM when_should) AS minute
  FROM guest_messages_sms
  WHERE when_should >= '2018-10-01'
  AND when_should < '2018-11-01'
  GROUP BY minute ORDER BY minute;
  """
  def context_stuff(from_date, to_date):
    context = {}
    with connection.cursor() as cursor:
      Row = namedtuple('Row', 'avg_delay day')
      cursor.execute((
          "SELECT SUM(when_did - when_should) / COUNT(1) AS avg_delay, "
          "date_trunc('day', when_should) AS day "
          "FROM (SELECT when_did, when_should FROM guest_messages_sms "
          "WHERE when_should >= %s AND when_should < %s "
          "AND when_did IS NOT NULL UNION "
          "SELECT when_did, when_should FROM guest_messages_email "
          "WHERE when_should >= %s AND when_should < %s "
          "AND when_did IS NOT NULL) as messages "
          "GROUP BY day ORDER BY day;"), [
              from_date, to_date, from_date, to_date])
      context['delays_by_day'] = [
          Row(row[0].seconds / 60, row[1].date) for row in cursor.fetchall()]
    context['todays_messages'] = (
        Email.objects.todays_messages() + SMS.objects.todays_messages())
    return context
  return simple_date_range_admin_page(
      request,
      from_date_str, to_date_str,
      date.today() - timedelta(days=30), date.today(),
      'message_delays', 'Guest message delays', 'message_delays.html',
      context_stuff)


def unsubscribe(request):
  """ This gets called when somebody clicks the unsubscribe link on a Mandrill
  transactional email. Mandrill then knows not to send further emails to them,
  but we should track it on our side too I guess. """
  notify(
      'dave@stayd.com',
      'Somebody unsubscribed', (
          'Uh... write some software that knows what to do with this. '
          'md_id {}, md_email {}, get {}, post {}').format(
              request.GET.get('md_id', ''), request.GET.get('md_email', ''),
              request.GET, request.POST))
  return HttpResponse('Ok.')
