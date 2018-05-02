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
gget(
    "reservations?filters={\"field\":\"status\",\"operator\":\"$in\","
    "\"value\":[\"confirmed\"]}")
"""


def gget(url):
  """ This is just a helper function for the shell. """
  return GuestyAPIGetter().get(url)


def gpost(url, data):
  """ This is just a helper function for the shell. """
  return GuestyAPIGetter().post(url, data)


def gput(url, data):
  """ This is just a helper function for the shell. """
  return GuestyAPIGetter().put(url, data)


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
        self._guesty_url(url), data=data, auth=self._guesty_auth())

  def put(self, url, data):
    return requests.put(
        self._guesty_url(url), data=data, auth=self._guesty_auth())

  def _guesty_url(self, endpoint):
    if endpoint and endpoint[0] == '/':
      endpoint = endpoint[1:]
    return 'https://api.guesty.com/api/v2/' + endpoint

  def _guesty_auth(self):
    # "Use your API key as the username and secret as the password."
    return (settings.GUESTY_KEY, settings.GUESTY_SECRET)


class GuestyAPI(object):
  def sync_listings(self, api_getter):
    self._sync_things(api_getter, Listing)

  def sync_reservations(self, api_getter):
    self._sync_things(api_getter, Reservation)

  def _sync_things(self, api_getter, type_of_thing):
    skip = 0
    limit = 25
    results = []
    while skip == 0 or len(results) == limit:
      results = api_getter.get_many(type_of_thing, skip, limit)
      for thing in results:
        if type_of_thing is Listing:
          self._sync_listing(thing)
        elif type_of_thing is Reservation:
          self._sync_reservation(api_getter, thing)
        else:
          raise Exception(
              'Not sure what to do with a {}'.format(type_of_thing))
      skip += len(results)

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

  def _sync_reservation(self, api_getter, r_short):
    channel_id = r_short['confirmationCode']
    reservation = Reservation.objects.filter(
        channel_reservation_id=channel_id).first()
    if reservation:
      guest = reservation.guest
    else:
      reservation = Reservation(channel_reservation_id=channel_id)
      guest = Guest()
    reservation.guest = self._sync_guest(api_getter, guest, r_short['guestId'])

    guesty_id = r_short['_id']
    r_long = api_getter.get_one(Reservation, guesty_id)

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
    reservation.status = r_long['status']
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
