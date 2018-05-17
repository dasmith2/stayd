from datetime import time
import json
from math import isclose

from django.conf import settings
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from djmoney.money import Money
import requests

from guest_messages.models import Message
from guests.models import Guest
from guesty.models import GuestyRental, GuestyReservation, GuestyGuest
from listings.models import Listing
from owner_payouts.models import ReservationToPayout
from rentals.models import Rental
from reservations.models import Reservation, ReservationLineItem
from util.channels import AIRBNB


"""
Just for the record, here's how you do a single custom filter on a reservation.
They still haven't gotten back to me about how to do more than one. Aaaaand
I discovered it doesn't even work.

curl -g "https://api.guesty.com/api/v2/reservations?filters={\"field\":\"status\",\"operator\":\"$in\",\"value\":[\"confirmed\"]}&skip=41&limit=1&fields=status" -u "1bcc904cc16621d26404458d7f3d53f6:e43d2f9c497b27f1a413c62c38b12d82" | grep -o -P 'status.{0,11}'  # noqa: E501

At this moment, that's printing out the status 'inquiry'.

At this moment, this works to set a custom field on a reservation.

gput('reservations/5ade4c82752e240089179c90', {"customFields": [{"fieldId": "5aea4193743fa3002a7debbb", "value": "999-999-8888", "_id": "5aecbc19967d6c00266a2b06"}]}).content  # noqa: E501


The following section is just for helper functions that make working in the
shell easier.
"""


def gget(url):
  """ gget('reservations') """
  return GuestyAPIGetter().get(url)


def gpost(url, data):
  return GuestyAPIGetter().post(url, data)


def gput(url, data):
  return GuestyAPIGetter().put(url, data)


def get_one(type_of_thing, guesty_id):
  """ get_one(Reservation, '5adf4893a67833002fae7393') """
  return GuestyAPIGetter().get_one(type_of_thing, guesty_id)


def sync_reservations(guesty_id=None, skip=0):
  if guesty_id:
    api_getter = GuestyAPIGetter()
    r = api_getter.get_one(Reservation, guesty_id)
    GuestySync(api_getter).sync_reservation(r, True)
  else:
    GuestySync().sync_reservations(skip=skip, verbose=True)


"""
These are classes which are good for unit testing, wiring into the server,
and so on.
"""


GUESTY_EVENTS = [
    'guest.created',
    'guest.deleted',
    'guest.updated',
    'listing.new',
    'listing.updated',
    'listing.removed',
    'payments.failed',
    'reservation.messageReceived',
    'reservation.new',
    'reservation.updated',
    'reservation.messageSent',
    'reservation.reviewed',
    'task.created',
    'task.deleted',
    'task.updated']


class GuestyAPIGetter(object):
  def get_one(self, type_of_thing, guesty_id):
    if type_of_thing is Listing:
      endpoint = 'listings'
    elif type_of_thing is Reservation:
      endpoint = 'reservations'
    elif type_of_thing is Guest:
      endpoint = 'guests'
    else:
      raise Exception('Not sure what to do with a {}'.format(type_of_thing))
    return self.get('{}/{}'.format(endpoint, guesty_id)).json()

  def get_many(self, type_of_thing, skip, limit):
    if type_of_thing is Listing:
      url_start = 'listings?'
    elif type_of_thing is Reservation:
      url_start = (
          'reservations?filters='
          '{"field":"status","operator":"$in","value":["confirmed"]}&')
    elif type_of_thing == 'Webhook':
      raise Exception(
          'Webhooks don\'t have paging, so just get_all(\'Webhook\')')
    else:
      raise Exception('Not sure what to do with a {}'.format(type_of_thing))
    url = url_start + 'skip={}&limit={}'.format(skip, limit)
    return self.get(url).json()['results']

  def get_all(self, type_of_thing):
    if type_of_thing == 'Webhook':
      return self.get('webhooks').json()

    to_return = []

    limit = 25
    skip = 0
    results = self.get_many(type_of_thing, skip, limit)
    while len(results):
      to_return.extend(results)
      skip += len(results)
      results = self.get_many(type_of_thing, skip, limit)

    return to_return

  def get(self, url):
    return requests.get(self._guesty_url(url), auth=self._guesty_auth())

  def post(self, url, data):
    return requests.post(
        self._guesty_url(url), json=data, auth=self._guesty_auth())

  def put(self, url, data):
    return requests.put(
        self._guesty_url(url), json=data, auth=self._guesty_auth())

  def delete(self, url):
    return requests.delete(self._guesty_url(url), auth=self._guesty_auth())

  def _guesty_url(self, endpoint):
    if endpoint and endpoint[0] == '/':
      endpoint = endpoint[1:]
    return 'https://api.guesty.com/api/v2/' + endpoint

  def _guesty_auth(self):
    # "Use your API key as the username and secret as the password."
    if not settings.GUESTY_KEY or not settings.GUESTY_SECRET:
      raise Exception(
          'You need the GUESTY_KEY and GUESTY_SECRET settings. '
          'See stayd/settings.py')
    return (settings.GUESTY_KEY, settings.GUESTY_SECRET)


class GuestySync(object):
  def __init__(self, api_getter=GuestyAPIGetter()):
    self.api_getter = api_getter

  def sync_listings(self, skip=0, verbose=False):
    self._sync_things(Listing, skip, verbose)

  def sync_reservations(self, skip=0, verbose=False):
    self._sync_things(Reservation, skip, verbose)

  def _handle_custom_fields(self, reservation, custom_fields):
    """ custom_fields is, like [{'fieldId': '5afa2c379ebb42009e34f270',
    'value': True, '_id': '5afc7708bbf3af002af8f0c9'}] _id is useless
    here. Forgive all the double negatives. Guesty has a quirk where
    custom boolean fields on a reservation must default to False. We want
    admins to be able to turn off specific automatic smss, or all of them,
    from Guesty. """
    all_messages_off = False
    id_verified = False
    for custom_field in custom_fields:
      field_id = custom_field['fieldId']
      if field_id == settings.DEACTIVATE_ALL_AUTOMATIONS_FIELD_ID:
        all_messages_off = custom_field['value']
      elif field_id == settings.ID_VERIFIED_FIELD_ID:
        id_verified = custom_field['value']
    if reservation.id_verified != id_verified:
      reservation.id_verified = id_verified
      reservation.save()
    for message in Message.objects.get_for_reservation(reservation):
      specific_off = all_messages_off
      if not specific_off:
        for custom_field in custom_fields:
          if custom_field['fieldId'] == message.guesty_custom_field_id:
            specific_off = custom_field['value']
      if bool(message.green_light) != bool(not specific_off):  # xor
        message.green_light = not specific_off
        message.save()

  def sync_reservation(self, r_short, verbose=False):
    guesty_id = r_short['_id']
    if 'money' in r_short:
      r_long = r_short
    else:
      r_long = self.api_getter.get_one(Reservation, guesty_id)
    status = r_long['status']
    if status != 'confirmed':
      if verbose:
        print('  Not syncing. The status is {}'.format(status))
      return

    channel_id = r_short['confirmationCode']
    reservation = Reservation.objects.filter(
        channel_reservation_id=channel_id).first()
    if reservation:
      guest = reservation.guest
    else:
      reservation = Reservation(channel_reservation_id=channel_id)
      guest = Guest()
    reservation.guest = self._sync_guest(guest, r_short['guestId'])

    reservation.check_in = parse_datetime(r_short['checkIn'])
    reservation.check_out = parse_datetime(r_short['checkOut'])
    reservation.booked_at = parse_datetime(r_long['confirmedAt'])

    reservation.planned_arrival = self._get_planned_arrival(r_long)

    reservation.night_count = (
        reservation.check_out.date() - reservation.check_in.date()).days
    reservation.reservation_created = parse_datetime(r_long['createdAt'])
    our_cut = r_long['money']['hostPayout']
    reservation.total_payin = Money(our_cut, r_long['money']['currency'])
    successful_payments = 0
    # Rarely, you do get multiple payments for the same reservation.
    for payment in r_long.get('money', {}).get('payments', []):
      if payment.get('status', '') == 'SUCCEEDED':
        successful_payments += payment.get('amount', 0)
    reservation.is_paid_in = isclose(successful_payments, our_cut)
    reservation.status = status
    reservation.listing = self._get_listing_from_reservation(r_long)

    reservation.save()

    Message.objects.create_for_reservation(reservation)
    self._handle_custom_fields(reservation, r_long['customFields'])
    self._sync_reservation_line_items(reservation, r_long)
    ReservationToPayout.objects.get_for_reservation(
        reservation).update_payout()
    GuestyReservation.objects.get_or_create(
        reservation=reservation, guesty_id=guesty_id)

  def _get_planned_arrival(self, r_long):
    planned_arrival_str = r_long.get('plannedArrival', None)
    if planned_arrival_str:  # '17:00'
      parts = list(int(p) for p in planned_arrival_str.split(':'))  # (17, 0)
      return time(*parts)
    return None

  def sync_webhooks(self, server_url, verbose=False, events=GUESTY_EVENTS):
    if server_url[-1] == '/':
      server_url = server_url[:-1]

    existing = self.api_getter.get_all('Webhook')
    expected = self._create_missing_webhooks_and_return_expected(
        server_url, existing, events, verbose)
    self._delete_extra_webhooks(server_url, existing, expected, verbose)

  def delete_webhooks(self, server_url, verbose=False):
    for webhook in self.api_getter.get_all('Webhook'):
      if webhook['url'].find(server_url) >= 0:
        if verbose:
          print('Deleting {}'.format(webhook))
        self.api_getter.delete('webhooks/{}'.format(webhook['_id']))

  def _create_missing_webhooks_and_return_expected(
      self, server_url, existing, events, verbose):
    expected = []
    account_ids = self._all_account_ids()
    for event_name in events:
      for account_id in account_ids:
        events = [event_name]
        expected.append({'accountId': account_id, 'events': events})

        found = False
        for exist in existing:
          found = found or all([
              exist['accountId'] == account_id,
              exist['events'] == events,
              exist['url'].find(server_url) >= 0])
        if not found:
          url = server_url + reverse(
              'guesty_webhook', kwargs={'event_name': event_name})
          new_hook = {
              'url': url, 'accountId': account_id, 'events': [event_name]}
          if verbose:
            print('Creating {}'.format(new_hook))
          self.api_getter.post('webhooks', new_hook)
    return expected

  def _delete_extra_webhooks(self, server_url, existing, expected, verbose):
    for exist in existing:
      if exist['url'].find(server_url) >= 0:
        found = False
        for expect in expected:
          accountId_match = exist['accountId'] == expect['accountId']
          events_match = exist['events'] == expect['events']
          if all([accountId_match, events_match]):
            found = True
            break
        if not found:
          if verbose:
            print('Deleting {}'.format(exist))
          self.api_getter.delete('webhooks/{}'.format(exist['_id']))

  def _sync_things(self, type_of_thing, skip, verbose):
    limit = 25
    results = self.api_getter.get_many(type_of_thing, skip, limit)
    while len(results):
      for index, thing in enumerate(results):
        if verbose:
          print('{}. Syncing {} {}'.format(
              index + skip, type_of_thing.__name__, thing['_id']))
        if type_of_thing is Listing:
          self.sync_listing(thing)
        elif type_of_thing is Reservation:
          self.sync_reservation(thing, verbose)
        else:
          raise Exception(
              'Not sure what to do with a {}'.format(type_of_thing))
      skip += len(results)
      results = self.api_getter.get_many(type_of_thing, skip, limit)

  def sync_listing(self, l):
    address = l['address']['full']
    rental = Rental.objects.filter(
        airbnb_address_scrape=address).first()
    if not rental:
      rental = Rental(airbnb_address_scrape=address)
    rental.time_zone = l['timezone']
    rental.currency = l['prices']['currency']
    rental.accommodates = l['accommodates']
    rental.bathrooms = l['bathrooms']
    rental.bedrooms = l['bedrooms']
    rental.property_type = l['propertyType']
    rental.room_type = l['roomType']
    rental.save()
    GuestyRental.objects.get_or_create(rental=rental, guesty_id=l['_id'])
    for channel in l['integrations']:
      if channel['platform'] == 'airbnb':
        listing_id = channel['airbnb']['id']
        listing = Listing.objects.filter(
            channel_listing_id=listing_id, channel=AIRBNB).first()
        if not listing:
          listing = Listing(
              channel_listing_id=listing_id, channel=AIRBNB,
              rental=rental)
        elif listing.rental.pk != rental.pk:
          raise Exception((
              'Existing listing {} is about to have its rental changed '
              'from {} to {} which makes no sense.').format(
                  listing.pk, listing.rental.pk, rental.pk))
        listing.title = l['title']
        listing.save()
      elif channel['platform'] == 'rentalsUnited':
        pass
      else:
        raise Exception((
            'I\'m not sure how to handle {} in the '
            'platform field yet. {}').format(
                channel['platform'], json.dumps(l['integrations'])))

  def _get_listing_from_reservation(self, r_long):
    channel = r_long['integration']['platform'].title()
    if channel == AIRBNB:
      listing_id = r_long['integration']['airbnb']['listingId']
      listings = Listing.objects.filter(channel_listing_id=listing_id)
      if listings:
        return listings[0]
      self.sync_listing(self.api_getter.get_one(Listing, r_long['listingId']))
      listings = Listing.objects.filter(channel_listing_id=listing_id)
      if listings:
        return listings[0]
      raise Exception((
          'I tried to sync the listing for reservation {} '
          'but no dice.').format(r_long['_id']))
    else:
      raise Exception(
          'I\'m not sure how to handle channel %s yet.'.format(channel))

  def _sync_guest(self, guest, guesty_id):
    guesty_g = self.api_getter.get_one(Guest, guesty_id)
    if 'airbnb' not in guesty_g:
      raise Exception('Im not sure how to handle non-airbnb guests yet.')
    channel_id = guesty_g['airbnb']['id']
    guest = Guest.objects.filter(channel_id=channel_id).first()
    if not guest:
      guest = Guest.objects.filter(
          full_name=guesty_g['fullName'], phone=guesty_g['phone']).first()
    if not guest:
      guest = Guest()
    guest.channel_id = channel_id
    guest.first_name = guesty_g['firstName']
    guest.full_name = guesty_g['fullName']
    guest.phone = guesty_g['phone']
    guest.airbnb_says_theyre_from = guesty_g['hometown']
    guest.save()
    GuestyGuest.objects.get_or_create(guest=guest, guesty_id=guesty_g['_id'])
    return guest

  def _sync_reservation_line_items(self, reservation, r_long):
    ReservationLineItem.objects.filter(reservation=reservation).delete()
    for item in r_long.get('money', {}).get('invoiceItems', []):
      value = Money(item['amount'], item['currency'])
      ReservationLineItem.objects.create(
          name=item['title'],
          value=value,
          reservation=reservation)
      if item['title'] == 'Accommodation fare':
        reservation.price_per_night = value / reservation.night_count
        reservation.save()

  def _all_account_ids(self):
    account_ids = set()

    for listing in self.api_getter.get_all(Listing):
      account_ids.add(listing['accountId'])

    return account_ids
