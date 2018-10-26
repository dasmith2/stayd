import json

from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from rest_framework.parsers import JSONParser

from properly.models.cleaning import RawEvent, Cleaner
from util.background import background
from util.fake_admin import admin_context


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
def hours_and_pay_report(request):
  context = admin_context(
      'Hours and pay', cleaners=Cleaner.objects.all())
  return render(request, 'hours_and_pay_report.html', context=context)
