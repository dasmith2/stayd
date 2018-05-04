import json

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.parsers import JSONParser

from guesty.models import RawEvent


@csrf_exempt
def save_event(request):
  data = JSONParser().parse(request)
  RawEvent.objects.create(
      json=json.dumps(data), headers='{}'.format(request.META))
  return HttpResponse('')
