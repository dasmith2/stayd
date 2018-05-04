import json
from math import isclose

from django.conf import settings
from django.utils.dateparse import parse_datetime
from djmoney.money import Money
import requests

from guests.models import Guest
from guesty.models import GuestyRental, GuestyReservation, GuestyGuest
from listings.models import Listing
from rentals.models import Rental
from reservations.models import Reservation, ReservationLineItem
from util.channels import AIRBNB


"""
Just for the record, here's how you do a single custom filter on a reservation.
They still haven't gotten back to me about how to do more than one. Aaaaand
I discovered it doesn't even work.

curl -g "https://api.guesty.com/api/v2/reservations?filters={\"field\":\"status\",\"operator\":\"$in\",\"value\":[\"confirmed\"]}&skip=41&limit=1&fields=status" -u "1bcc904cc16621d26404458d7f3d53f6:e43d2f9c497b27f1a413c62c38b12d82" | grep -o -P 'status.{0,11}'  # noqa: E501

At this moment, that's printing out the status 'inquiry'.


The following section is just for helper functions that make working in the
shell easier.


gput('reservations/5ade4c4214fe0e004dcde56a', {"customFields": [{"fieldId":"5aea4193743fa3002a7debbb", "value": "777-777-7777"}]}).content
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
    GuestyAPI()._sync_reservation(api_getter, r, True)
  else:
    GuestyAPI().sync_reservations(skip=skip, print_progress=True)


"""
These are classes which are good for unit testing, wiring into the server,
and so on.
"""


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
    else:
      raise Exception('Not sure what to do with a {}'.format(type_of_thing))
    url = url_start + 'skip={}&limit={}'.format(skip, limit)
    return self.get(url).json()['results']

  def get(self, url):
    return requests.get(self._guesty_url(url), auth=self._guesty_auth())

  def post(self, url, data):
    return requests.post(
        self._guesty_url(url), json=data, auth=self._guesty_auth())

  def put(self, url, data):
    return requests.put(
        self._guesty_url(url), json=data, auth=self._guesty_auth())

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


class GuestyAPI(object):
  def sync_listings(self, api_getter=None, skip=0, print_progress=False):
    self._sync_things(
        api_getter or GuestyAPIGetter(), Listing, skip, print_progress)

  def sync_reservations(self, api_getter=None, skip=0, print_progress=False):
    self._sync_things(
        api_getter or GuestyAPIGetter(), Reservation, skip, print_progress)

  def _sync_things(self, api_getter, type_of_thing, skip, print_progress):
    limit = 25
    results = api_getter.get_many(type_of_thing, skip, limit)
    while len(results):
      for index, thing in enumerate(results):
        if print_progress:
          print('{}. Syncing {} {}'.format(
              index + skip, type_of_thing.__name__, thing['_id']))
        if type_of_thing is Listing:
          self._sync_listing(thing)
        elif type_of_thing is Reservation:
          self._sync_reservation(api_getter, thing, print_progress)
        else:
          raise Exception(
              'Not sure what to do with a {}'.format(type_of_thing))
      skip += len(results)
      results = api_getter.get_many(type_of_thing, skip, limit)

  def _sync_listing(self, l):
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
      else:
        raise Exception((
            'I\'m not sure how to handle {} in the '
            'platform field yet. {}').format(
                l['platform'], json.dumps(l['integrations'])))

  def _sync_reservation(self, api_getter, r_short, print_progress):
    guesty_id = r_short['_id']
    r_long = api_getter.get_one(Reservation, guesty_id)
    status = r_long['status']
    if status != 'confirmed':
      if print_progress:
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
    reservation.guest = self._sync_guest(api_getter, guest, r_short['guestId'])

    reservation.check_in = parse_datetime(r_short['checkIn'])
    reservation.check_out = parse_datetime(r_short['checkOut'])
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
    reservation.listing = self._get_listing_from_reservation(
        api_getter, r_long)

    reservation.save()

    self._sync_reservation_line_items(reservation, r_long)
    reservation.update_payout()
    GuestyReservation.objects.get_or_create(
        reservation=reservation, guesty_id=guesty_id)

  def _get_listing_from_reservation(self, api_getter, r_long):
    channel = r_long['integration']['platform'].title()
    if channel == AIRBNB:
      listing_id = r_long['integration']['airbnb']['listingId']
      listings = Listing.objects.filter(channel_listing_id=listing_id)
      if listings:
        return listings[0]
      self._sync_listing(api_getter.get_one(Listing, r_long['listingId']))
      listings = Listing.objects.filter(channel_listing_id=listing_id)
      if listings:
        return listings[0]
      raise Exception((
          'I tried to sync the listing for reservation {} '
          'but no dice.').format(r_long['_id']))
    else:
      raise Exception(
          'I\'m not sure how to handle channel %s yet.'.format(channel))

  def _sync_guest(self, api_getter, guest, guesty_id):
    guesty_g = api_getter.get_one(Guest, guesty_id)
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
