from datetime import date
import json

from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import render, reverse, redirect
from django.views.decorators.csrf import csrf_exempt
from rest_framework.parsers import JSONParser

from properly.models.cleaning import RawEvent, Cleaning
from util.background import background
from util.fake_admin import admin_context
from util.urls import date_to_url_str, dates_from_strs, date_to_date_picker_str


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
  RawEvent.objects.create(json=data_str)


@staff_member_required
def hours_and_pay_report(request, from_date_str='', to_date_str=''):
  if not from_date_str and not to_date_str:
    return redirect(reverse('hours_and_pay_report', kwargs={
        'from_date_str': date_to_url_str(date.today().replace(day=1)),
        'to_date_str': date_to_url_str(date.today())}))

  from_date, to_date = dates_from_strs(from_date_str, to_date_str)

  context = admin_context(
      'Hours and pay',
      hours_and_pay=Cleaning.objects.hours_and_pay(from_date, to_date),
      from_date_str=date_to_date_picker_str(from_date),
      to_date_str=date_to_date_picker_str(to_date))
  return render(request, 'hours_and_pay_report.html', context=context)
