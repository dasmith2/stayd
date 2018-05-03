import copy

from django.test import TestCase
from django.utils.dateparse import parse_datetime
from djmoney.money import Money

from guests.models import Guest, GuestPhoneNumber
from guesty.api import GuestyAPI
from guesty.api_examples import (
    GUEST, LISTING, RESERVATION, RESERVATION_FOR_LIST)
from guesty.models import GuestyReservation, GuestyRental, GuestyGuest
from listings.models import Listing
from rentals.models import Rental
from reservations.models import Reservation
from util.channels import AIRBNB


class MockGuestyAPIGetter(object):
  def __init__(self):
    self.address = None
    self.listing_id = None

  def get_one(self, type_of_thing, guesty_id):
    if type_of_thing is Guest:
      to_return = GUEST
    elif type_of_thing is Reservation:
      to_return = RESERVATION
    elif type_of_thing is Listing:
      to_return = LISTING
    else:
      raise Exception('Not sure what to do with a {}'.format(type_of_thing))
    if to_return['_id'] != guesty_id:
      raise Exception(
          'Asked for {} {} but what I have is {} {}'.format(
              type_of_thing, guesty_id, type_of_thing, to_return['_id']))
    return to_return

  def get_many(self, type_of_thing, skip, limit):
    if skip > 0:
      return []
    if type_of_thing is Listing:
      listing = copy.deepcopy(LISTING)
      if self.address:
        listing['address']['full'] = self.address
      if self.listing_id:
        listing['_id'] = self.listing_id
      return [listing]
    elif type_of_thing is Reservation:
      return [RESERVATION_FOR_LIST]
    raise Exception('Not sure what to do with a {}'.format(type_of_thing))

  def set_address(self, address):
    self.address = address

  def set_listing_id(self, listing_id):
    self.listing_id = listing_id


class ListingTests(TestCase):
  def test_sync_listings(self):
    mock_getter = MockGuestyAPIGetter()
    mock_getter.set_address('221b Baker St., London, UK')
    mock_getter.set_listing_id('5e5e5e')

    self.assertEqual(0, Rental.objects.filter(
        airbnb_address_scrape='221b Baker St., London, UK').count())

    GuestyAPI().sync_listings(mock_getter)
    GuestyAPI().sync_listings(mock_getter)

    self.assertEqual(1, Rental.objects.filter(
        airbnb_address_scrape='221b Baker St., London, UK').count())

    rental = GuestyRental.objects.filter(guesty_id='5e5e5e').first().rental
    listing = Listing.objects.get(rental=rental, channel=AIRBNB)

    self.assertEqual(listing.channel, AIRBNB)
    self.assertEqual(listing.channel_listing_id, '21679272')
    self.assertEqual(
        listing.title, 'SPACIOUS 3BR/2BA **2 STOPS FROM NYC** SLEEPS 10!!!')

    self.assertEqual(
        rental.airbnb_address_scrape, '221b Baker St., London, UK')
    self.assertEqual(rental.time_zone, 'America/New_York')
    self.assertEqual(rental.currency, 'BZD')
    self.assertEqual(rental.accommodates, 10)
    self.assertEqual(rental.bathrooms, 2)
    self.assertEqual(rental.bedrooms, 3)
    self.assertEqual(rental.property_type, 'Apartment')
    self.assertEqual(rental.room_type, 'Entire home/apt')


class ReservationTests(TestCase):
  def test_sync_reservation(self):
    mock_getter = MockGuestyAPIGetter()

    self.assertEqual(0, Reservation.objects.filter(
        channel_reservation_id='HM123456').count())

    GuestyAPI().sync_reservations(mock_getter)
    GuestyAPI().sync_reservations(mock_getter)

    self.assertEqual(1, Reservation.objects.filter(
        channel_reservation_id='HM123456').count())

    reservation = GuestyReservation.objects.filter(
        guesty_id='5ade4d3314fe0e004dcde909').first().reservation

    self.assertEqual(reservation.channel_reservation_id, 'HM123456')
    self.assertEqual(
        reservation.check_in, parse_datetime('2018-01-03T20:00:00.000Z'))
    self.assertEqual(
        reservation.check_out, parse_datetime('2018-01-12T16:00:00.000Z'))
    self.assertEqual(reservation.reservation_created, parse_datetime(
        '2018-04-23T21:16:35.273Z'))
    # 140.22 is 1262 / 9 rounded
    self.assertEqual(reservation.price_per_night, Money(140.22, 'BZD'))
    self.assertEqual(reservation.night_count, 9)
    self.assertEqual(reservation.total_payin, Money(1321.14, 'BZD'))
    self.assertEqual(reservation.is_paid_in, True)
    self.assertEqual(reservation.status, 'confirmed')
    self.assertEqual(
        reservation.listing.rental.airbnb_address_scrape,
        '144 Steuben Street Apt #402, Jersey City, NJ 07302, United States')

    guest = reservation.guest

    self.assertEqual(guest.full_name, 'Sofia Fay')
    self.assertEqual(
        guest.airbnb_says_theyre_from, 'Tortola, British Virgin Islands')
    self.assertEqual(guest.phone, '16178177271')
    self.assertEqual(
        GuestPhoneNumber.objects.filter(guest=guest)[0].raw_string,
        '16178177271')
    self.assertEqual(guest.channel_id, '92547277')

    self.assertEqual(
        GuestyGuest.objects.get(guesty_id='5ade4ca7a989550061844c3b').guest.pk,
        guest.pk)

    got_line_items = reservation.line_items().order_by('name')
    got = [(li.name, li.value) for li in got_line_items]
    expected = [
        ('Accommodation fare', Money(1262, 'BZD')),
        ('Cleaning fee', Money(100, 'BZD')),
        ('Host channel fee', Money(-40.86, 'BZD'))]
    self.assertEqual(expected, got)
