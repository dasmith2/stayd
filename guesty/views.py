import json
import sys

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.parsers import JSONParser

from errors.models import log_error
from guesty.api import GuestySync
from guesty.models import RawEvent


@csrf_exempt
def guesty_webhook(request, event_name):
  data = JSONParser().parse(request)
  data_str = json.dumps(data)

  # Save the raw event first in case there's a problem processing it.
  # Then we can go back through and fix the problem.
  raw_event = RawEvent.objects.create(json=data_str, event_name=event_name)

  handled = False
  try:
    handled = GuestySync().handle_raw_event(raw_event)
  except Exception:
    # This happens a lot, so don't raise an exception and trigger an
    # email every time.
    raw_event_helpful = (
        'heroku run python manage.py shell -a stayd-prod\n'
        'from guesty.api import GuestySync\n'
        'from guesty.models import RawEvent\n'
        'GuestySync().handle_raw_event(RawEvent.objects.get(pk={}))').format(
            raw_event.pk)
    # I used to put data_str in here, but that quickly became unhelpful as
    # Guesty included more and more, like, historical log nonsense in these
    # webhooks.
    log_error(
        'Error handling {} webhook'.format(event_name),
        raw_event_helpful, sys.exc_info())
  if handled:
    return HttpResponse(json.dumps({'message': handled}))
  else:
    return HttpResponse(
        json.dumps({'message': 'I saved this as a raw event.'}))
