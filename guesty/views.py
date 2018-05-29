import json
import sys

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.parsers import JSONParser

from errors.models import log_error
from guesty.api import GuestySync
from guesty.models import RawEvent
from guesty.front_contact_updater import FrontContactUpdater


@csrf_exempt
def guesty_webhook(request, event_name):
  data = JSONParser().parse(request)
  data_str = json.dumps(data)

  # Save the raw event first in case there's a problem processing it.
  # Then we can go back through and fix the problem.
  raw_event = RawEvent.objects.create(json=data_str, event_name=event_name)

  handled = False
  try:
    if event_name.find('reservation') >= 0 and 'reservation' in data:
      reservation = GuestySync().sync_reservation(data['reservation'])
      if event_name == 'reservation.new':
        FrontContactUpdater().update_for_guest(reservation.guest)
      handled = 'I synced this reservation.'
    elif event_name.find('listing') >= 0 and 'listing' in data:
      # This used to be GuestySync().sync_listing(data['listing']) but
      # sometimes the listing.updated event is just, like, {"listing": {"_id":
      # "5af600adf78694001ba03984", "accountId": "5af3858b36385d001f17fea0",
      # "customFields": []}, "event": "listing.updated"}
      GuestySync().sync_listing(data['listing']['_id'])
      handled = 'I synced this listing.'
  except Exception:
    # This happens a lot, so don't raise an exception and trigger an
    # email every time.
    log_error(
        'Error handling {} webhook'.format(event_name),
        data_str, sys.exc_info())
  if handled:
    raw_event.handled = True
    raw_event.save()
    return HttpResponse(
        json.dumps({'message': handled}))
  else:
    return HttpResponse(
        json.dumps({'message': 'I saved this as a raw event.'}))
