from datetime import date
import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.parsers import JSONParser

from properly.models.cleaning import RawEvent, Cleaning
from util.background import background
from util.admin import simple_date_range_admin_page


@csrf_exempt
def properly_webhook(request):
  if request.META['REQUEST_METHOD'] == 'POST':
    do_properly_webhook(JSONParser().parse(request))
  return JsonResponse({'ok': True})


@background
def do_properly_webhook(data):
  data_str = json.dumps(data)

  # Save the raw event first in case there's a problem processing it.
  # Then we can go back through and fix the problem.
  raw = RawEvent.objects.create(json=data_str)

  raw.handle()


def hours_and_pay_report(request, from_date_str='', to_date_str=''):
  def hours_and_pay_report_context_stuff(from_date, to_date):
    return {
        'hours_and_pay': Cleaning.objects.hours_and_pay(from_date, to_date)}
  return simple_date_range_admin_page(
      request,
      from_date_str, to_date_str, date.today().replace(day=1), date.today(),
      'hours_and_pay_report', 'Hours and pay', 'hours_and_pay_report.html',
      hours_and_pay_report_context_stuff)
