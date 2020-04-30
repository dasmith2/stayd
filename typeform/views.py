import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from rest_framework.parsers import JSONParser

from typeform.models import RawEvent, Response
from util.admin import admin_context
from util.background import background
from util.permission import is_superuser


@csrf_exempt
def typeform_webhook(request):
  data = JSONParser().parse(request)
  data_str = json.dumps(data)
  handle_raw_event_background(RawEvent.objects.create(json=data_str).pk)
  return JsonResponse({'ok': True})


@background
def handle_raw_event_background(webhook_id):
  RawEvent.objects.get(pk=webhook_id).handle()


@is_superuser
def see_response(request, pk):
  response = Response.objects.get(pk=pk)
  context = admin_context('Typeform response', response=response)
  return render(
      request, 'see_response.html', context=context)


@is_superuser
def see_raw_event(request, pk):
  return RawEvent.objects.get(pk=pk).as_html()
