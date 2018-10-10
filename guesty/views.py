import json
import sys

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.parsers import JSONParser

from errors.models import log_error
from guesty.guesty import Guesty
from guesty.models import RawEvent
from reservations.syncer import ReservationManagerIsDown
from util.background import background


@csrf_exempt
def guesty_webhook(request, event_name):
  data = JSONParser().parse(request)
  do_guesty_webhook(event_name, data)
  return JsonResponse({'ok': True})


@background
def do_guesty_webhook(event_name, data):
  """ After creating
  https://keystothekingdom.stayd.com/admin/performance/longrequest/
  it became real obvious real quick that these need to be in the
  background! """
  if 'reservation' in data:
    if 'log' in data['reservation']:
      # The log is useless and gets quite large. This makes working in the
      # shell a little easier. I also do this in get_one in
      # guesty.api.GuestyAPI
      del data['reservation']['log']
  data_str = json.dumps(data)

  # Save the raw event first in case there's a problem processing it.
  # Then we can go back through and fix the problem.
  raw_event = RawEvent.objects.create(json=data_str, event_name=event_name)

  try:
    Guesty().handle_raw_event(raw_event)
  except ReservationManagerIsDown:
    # A reservation webhook doesn't include guest details, so we try to pull
    # the guest from Guesty. If we can't, just leave this webhook un-handled
    # and let circle_back_around get it.
    pass
  except Exception:
    # This happens a lot, so don't raise an exception and trigger an
    # email every time.
    raw_event_helpful = (
        'heroku run python manage.py shell -a stayd-prod\n'
        'from guesty.guesty import Guesty\n'
        'from guesty.models import RawEvent\n'
        'Guesty().handle_raw_event(RawEvent.objects.get(pk={}))').format(
            raw_event.pk)
    # I used to put data_str in here, but that quickly became unhelpful as
    # Guesty included more and more, like, historical log nonsense in these
    # webhooks.
    log_error(
        'Error handling {} webhook'.format(event_name),
        raw_event_helpful, sys.exc_info())
