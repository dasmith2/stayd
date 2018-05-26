from datetime import time
import json
from math import isclose
import re

from django.conf import settings
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from djmoney.money import Money
import requests

from guest_messages.models import Message, ReservationSyncer
from guests.models import Guest
from guesty.custom_fields import CustomFields
from guesty.models import GuestyRental, GuestyReservation, GuestyGuest
from listings.models import Listing
from owner_payouts.models import ReservationToPayout
from rentals.models import Rental
from reservations.models import Reservation, ReservationLineItem
from util.channels import AIRBNB, GUESTY, BOOKINGCOM, SHORT_CHANNEL_NAMES
from util.tests import is_test


"""
Guesty is our Channel Manager, meaning it helps us interface with all the
channels such as Airbnb and Booking.com. We can't get access to the Airbnb
API, not in a straightforward sane above board way anyway. Guesty is also our
property management system (PMS).

This file has all our logic for talking with Guesty. For instance, it knows
how to sync reservations.

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


def get_json_for_reservation(reservation):
  guesty_id = GuestyReservation.objects.get(reservation=reservation).guesty_id
  return get_one(Reservation, guesty_id)


def sync_reservation(guesty_id):
  api_getter = GuestyAPIGetter()
  r = api_getter.get_one(Reservation, guesty_id)
  GuestySync(api_getter).sync_reservation(r, True)


def sync_reservations(skip=0):
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
    got = self.get('{}/{}'.format(endpoint, guesty_id)).json()
    if 'log' in got:
      # The log is useless and gets quite large. This makes working in the
      # shell a little easier.
      del got['log']
    return got

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
    if not is_test():
      return requests.get(self._guesty_url(url), auth=self._guesty_auth())

  def post(self, url, data):
    if not is_test():
      return requests.post(
          self._guesty_url(url), json=data, auth=self._guesty_auth())

  def put(self, url, data):
    if not is_test():
      return requests.put(
          self._guesty_url(url), json=data, auth=self._guesty_auth())

  def delete(self, url):
    if not is_test():
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


class GuestySync(ReservationSyncer):
  def __init__(self, api_getter=GuestyAPIGetter()):
    self.api_getter = api_getter

  def sync_listings(self, skip=0, verbose=False):
    self._sync_things(Listing, skip, verbose)

  def sync_reservations(self, skip=0, verbose=False):
    self._sync_things(Reservation, skip, verbose)

  def _handle_custom_fields(self, reservation, custom_fields):
    if reservation.auto_communicate != custom_fields.temporary_allow_sms():
      reservation.auto_communicate = custom_fields.temporary_allow_sms()
      reservation.save()
    if reservation.id_verified != custom_fields.id_verified():
      reservation.id_verified = custom_fields.id_verified()
      reservation.save()
    if reservation.guest.email != custom_fields.email_provided():
      reservation.guest.email = custom_fields.email_provided()
      reservation.guest.save()
    provided_phone = custom_fields.phone_provided()
    if provided_phone and reservation.guest.phone != provided_phone:
      reservation.guest.set_primary_phone(provided_phone)
    if custom_fields.paid_in_full() != reservation.is_paid_in:
      custom_fields.set_paid_in_full(reservation.is_paid_in)
    if custom_fields.credit_card_authorization_valid() != bool(
        reservation.security_deposit):
      custom_fields.set_credit_card_authorization_valid(bool(
          reservation.security_deposit))
    custom_fields.send_changes(self.api_getter)

    self._handle_message_custom_fields(reservation, custom_fields)

  def _handle_message_custom_fields(self, reservation, custom_fields):
    sms_enabled = custom_fields.sms_enabled()
    for message in Message.objects.get_for_reservation(reservation):
      specific_enabled = sms_enabled and custom_fields.get(
          message.guesty_custom_field_id, True)
      if message.green_light != specific_enabled:
        message.green_light = specific_enabled
        message.save()

  def sync_stayd_reservation(self, reservation):
    # There are sometimes two of these. What the heck!
    guestvation = GuestyReservation.objects.filter(
        reservation=reservation).first()
    guesty_id = guestvation.guesty_id
    guesty_r = self.api_getter.get_one(Reservation, guesty_id)
    return self.sync_reservation(guesty_r)

  def alert_send_sms_failed(self, reservation):
    custom_fields = self._get_custom_fields_for_reservation(reservation)
    custom_fields.set_send_sms_failed()
    custom_fields.send_changes(self.api_getter)

  def _get_custom_fields_for_reservation(self, reservation):
    guestvation = GuestyReservation.objects.get(reservation=reservation)
    guesty_id = guestvation.guesty_id
    guesty_r = self.api_getter.get_one(Reservation, guesty_id)
    return CustomFields(
        reservation, guesty_id, guesty_r['customFields'])

  def sync_reservation(self, r_short, verbose=False):
    guesty_id = r_short['_id']
    if 'money' in r_short:
      r_long = r_short
    else:
      r_long = self.api_getter.get_one(Reservation, guesty_id)

    status = r_long['status']
    if status == 'inquiry':
      # In this case there's no confirmation code yet or anything.
      return

    channel_id = r_short['confirmationCode']
    reservation = Reservation.objects.filter(
        channel_reservation_id=channel_id).first()

    if status != 'confirmed':
      if reservation:
        reservation.status = status
        reservation.save()
        if verbose:
          print('  Setting status to {}, but that\'t it.'.format(status))
      elif verbose:
        print('  Not syncing. The status is {}'.format(status))
      return

    if reservation:
      guest = reservation.guest
    else:
      reservation = Reservation(channel_reservation_id=channel_id)
      guest = Guest()

    custom_fields = CustomFields(
        reservation, r_long['_id'], r_long['customFields'])
    guesty_g = self.api_getter.get_one(Guest, r_long['guestId'])
    reservation.guest = self._sync_guest(guest, guesty_g)
    # I know, confusing. Guesty's guest object has an anonymized channel
    # email, not the guests's actual email. We can get the guest's actual
    # email, but that's custom, so it's in a custom field.
    guesty_email = guesty_g.get('email', '')
    reservation.anonymized_email = guesty_email
    guest.email = custom_fields.email_provided()
    guest.save()

    reservation.check_in = parse_datetime(r_short['checkIn'])
    reservation.check_out = parse_datetime(r_short['checkOut'])
    reservation.booked_at = parse_datetime(r_long['confirmedAt'])

    reservation.planned_arrival = self._get_time(r_long, 'plannedArrival')
    reservation.planned_departure = self._get_time(r_long, 'plannedDeparture')

    reservation.night_count = (
        reservation.check_out.date() - reservation.check_in.date()).days
    reservation.reservation_created = parse_datetime(r_long['createdAt'])
    our_cut = r_long['money']['hostPayout']
    reservation.total_payin = Money(our_cut, r_long['money']['currency'])
    successful_payments = 0
    # Rarely, you do get multiple payments for the same reservation.
    for payment in r_long.get('money', {}).get('payments', []):
      pay_status = payment.get('status', '')
      if pay_status == 'SUCCEEDED':
        successful_payments += payment.get('amount', 0)
      elif pay_status == 'AUTHORIZATION_HOLD_SUCCEEDED':
        # I assume that any successful hold placed on a card is a security
        # deposit.
        reservation.security_deposit = Money(
            payment['amount'], payment['currency'])
    # Those payments appear to refer to payments from airbnb to us, not from
    # the guest to Airbnb. Hence, our_cut should roughly equal
    # successful_payments.
    reservation.is_paid_in = isclose(successful_payments, our_cut)
    reservation.status = status
    if r_long['source'] == 'Airbnb':
      reservation.display_channel = AIRBNB
    elif r_long['source'] == 'BookingCom':
      reservation.display_channel = BOOKINGCOM
    reservation.listing = self._get_listing_from_reservation(r_long)

    reservation.save()

    Message.objects.create_for_reservation(reservation)

    self._handle_custom_fields(reservation, custom_fields)
    self._sync_reservation_line_items(reservation, r_long)
    ReservationToPayout.objects.get_for_reservation(
        reservation).update_payout()
    # OK, apparently Guesty will destroy and create new objects for the
    # same reservation. I used to just have this here:
    # GuestyReservation.objects.get_or_create(
    #     reservation=reservation, guesty_id=guesty_id)
    # But that was no good because they'd send a totally new guesty_id for
    # the same channel_reservation_id, so I'd end up with two
    # GuestyReservations, the first being invalid.
    existing_gr = GuestyReservation.objects.filter(reservation=reservation)
    if existing_gr:
      existing_gr.update(guesty_id=guesty_id)
    else:
      GuestyReservation.objects.get_or_create(
          reservation=reservation, guesty_id=guesty_id)

  def _appears_to_be_anonymized_email(self, email):
    # So, like, @.*(airbnb|booking|homeaway)
    pattern = '@.*(' + '|'.join(SHORT_CHANNEL_NAMES) + ')'
    finder = re.compile(pattern, flags=re.IGNORECASE)
    return bool(finder.findall(email))

  def _get_time(self, r_long, key):
    time_str = r_long.get(key, None)
    if time_str:  # '17:00'
      parts = list(int(p) for p in time_str.split(':'))  # (17, 0)
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

  def sync_listing(self, listing_data):
    """ listing_data can be either a listing dict, or a listing id string. """
    if listing_data.__class__ is str:
      listing_data = self.api_getter.get_one(Listing, listing_data)
    address = listing_data['address']['full']
    rental = Rental.objects.filter(
        airbnb_address_scrape=address).first()
    if not rental:
      rental = Rental(airbnb_address_scrape=address)
    rental.city = listing_data['address']['city']
    rental.time_zone = listing_data['timezone']
    rental.currency = listing_data['prices']['currency']
    rental.accommodates = listing_data['accommodates']
    rental.bathrooms = listing_data['bathrooms']
    rental.bedrooms = listing_data['bedrooms']
    rental.property_type = listing_data['propertyType']
    rental.room_type = listing_data['roomType']
    rental.save()
    GuestyRental.objects.get_or_create(
        rental=rental, guesty_id=listing_data['_id'])
    if not listing_data['integrations']:
      channel_listing_id = listing_data['_id']
      self._create_listing(channel_listing_id, GUESTY, rental, listing_data)
    for channel in listing_data['integrations']:
      if channel['platform'] == 'airbnb':
        channel_listing_id = channel['airbnb']['id']
        self._create_listing(channel_listing_id, AIRBNB, rental, listing_data)
      elif channel['platform'] == 'rentalsUnited':
        pass
      else:
        raise Exception((
            'I\'m not sure how to handle {} in the '
            'platform field yet. {}').format(
                channel['platform'], json.dumps(listing_data['integrations'])))

  def _create_listing(self, channel_listing_id, channel, rental, listing_data):
    listing = Listing.objects.filter(
        channel_listing_id=channel_listing_id, channel=channel).first()
    if not listing:
      listing = Listing(
          channel_listing_id=channel_listing_id, channel=channel,
          rental=rental)
    elif listing.rental.pk != rental.pk:
      raise Exception((
          'Existing listing {} is about to have its rental changed '
          'from {} to {} which makes no sense.').format(
              listing.pk, listing.rental.pk, rental.pk))
    listing.title = listing_data['title']
    listing.save()
    return listing

  def _get_listing_from_reservation(self, r_long):
    channel = r_long['integration']['platform']
    if channel.title() == AIRBNB:
      channel_listing_id = r_long['integration']['airbnb']['listingId']
    elif channel == 'manual':
      # This is probably just the test listing, so use guesty's id as the
      # channel id.
      channel_listing_id = r_long['listingId']
    else:
      raise Exception(
          'I\'m not sure how to handle channel {} yet.'.format(channel))
    listings = Listing.objects.filter(channel_listing_id=channel_listing_id)
    if listings:
      return listings[0]
    self.sync_listing(self.api_getter.get_one(Listing, r_long['listingId']))
    listings = Listing.objects.filter(channel_listing_id=channel_listing_id)
    if listings:
      return listings[0]
    raise Exception((
        'I tried to sync the listing for reservation {} '
        'but no dice.').format(r_long['_id']))

  def _sync_guest(self, guest, guesty_g):
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
    guest.airbnb_says_theyre_from = guesty_g.get('hometown', '')
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
