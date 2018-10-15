import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.parsers import JSONParser

from properly.models import RawEvent
from util.background import background


@csrf_exempt
def properly_webhook(request):
  do_properly_webhook(JSONParser().parse(request))
  return JsonResponse({'ok': True})


@background
def do_properly_webhook(data):
  data_str = json.dumps(data)

  # Save the raw event first in case there's a problem processing it.
  # Then we can go back through and fix the problem.
  RawEvent.objects.create(json=data_str)
