import json
import sys

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from rest_framework.parsers import JSONParser

from errors.models import log_error
from guesty.guesty import Guesty
from guesty.models import RawEvent
from rentals.models import Rental
from reservations.syncer import ReservationManagerIsDown
from util.admin import admin_context
from util.background import background
from util.html_status_codes import ServerError


@csrf_exempt
def guesty_webhook(request, event_name):
  data = JSONParser().parse(request)

  """ After creating
  https://keys.hihoward.com/admin/performance/longrequest/
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

  do_guesty_webhook(event_name, raw_event.pk)

  return JsonResponse({'ok': True})


@background
def do_guesty_webhook(event_name, raw_event_id):
  raw_event = RawEvent.objects.get(pk=raw_event_id)
  try:
    Guesty().handle_raw_event(raw_event)
  except ReservationManagerIsDown:
    # A reservation webhook doesn't include guest details, so we try to pull
    # the guest from Guesty. If we can't, just leave this webhook un-handled
    # and let circle_back_around get it.
    pass
  except ServerError:
    # For instance, we create a booking with properly for each reservation, and
    # the properly server could throw a 500. Idea: we should make a fuss if a
    # webhook never gets handled even after a bunch of circle back arounds.
    pass
  except Exception:
    # This happens a lot, so don't raise an exception and trigger an
    # email every time.
    raw_event_helpful = (
        'https://keys.hihoward.com/admin/guesty/rawevent/'
        '{}/change/\n\n'
        'heroku run python manage.py shell -a stayd-prod\n\n'
        'import json\n'
        'from guesty.models import RawEvent\n'
        'raw = RawEvent.objects.get(pk={})\n'
        'json.loads(raw.json)\n\n'
        'from guesty.guesty import Guesty\n'
        'Guesty().handle_raw_event(raw)').format(
            raw_event.pk, raw_event.pk)
    # I used to put data_str in here, but that quickly became unhelpful as
    # Guesty included more and more, like, historical log nonsense in these
    # webhooks.
    log_error(
        'Error handling {} webhook'.format(event_name),
        raw_event_helpful, sys.exc_info())


@background
def turn_on_all_messages_background(rental, api=None):
  rental.guestyrental.turn_on_all_messages(api)


def turn_on_all_messages(request, api=None):
  message = None
  if 'rental_id' in request.POST:
    rental_id = int(request.POST['rental_id'])
    rental = Rental.objects.get(pk=rental_id)
    message = (
        'Turning on all guesty fields for all reservations for {}'.format(
            rental.nickname))
    turn_on_all_messages_background(rental, api)
  rentals = Rental.objects.filter(is_active=True).order_by('nickname')
  context = admin_context(
      'Turn on all custom fields etc. per rental', rentals=rentals,
      message=message)
  return render(request, 'turn_on_all_messages.html', context=context)
