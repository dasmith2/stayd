import json

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.parsers import JSONParser

from guesty.api import GuestySync
from guesty.models import RawEvent


@csrf_exempt
def guesty_webhook(request, event_name):
  data = JSONParser().parse(request)
  data_str = json.dumps(data)

  raw_event = RawEvent.objects.create(json=data_str, event_name=event_name)
  if event_name.find('reservation') >= 0 and 'reservation' in data:
    GuestySync().sync_reservation(data['reservation'])
    raw_event.handled = True
    raw_event.save()
    return HttpResponse(
        json.dumps({'message': 'I synced this reservation.'}))
  else:
    return HttpResponse(
        json.dumps({'message': 'I saved this as a raw event.'}))
