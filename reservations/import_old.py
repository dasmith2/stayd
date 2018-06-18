""" This is to import the reservations in oldBookingComReservations.csv
Once that's long since done, remove that file and this file. """
from collections import namedtuple
from datetime import datetime
import csv
import re

from django.utils.timezone import make_aware
from djmoney.money import Money

from guests.models import Guest
from listings.models import Listing
from rentals.models import Rental
from reservations.models import (
    Reservation, ReservationLineItem, KNOWN_LINE_ITEM_NAMES, CONFIRMED,
    CANCELED)
from util.channels import BOOKINGCOM


LOCATION_LOOKUP = {
    '144 Steuben Street Apt #402 Jersey City': '144 Steuben Street Apt #402',
    '144 Steuben Street Apt #603 Jersey City': '144 Steuben Street Apt #603',
    '144 Steuben Street Apt 601 Jersey City': '142 Steuben Street Apt 601',
    '185 Newark Avenue Apartment #4 Jersey City':
        '185 Newark Avenue Apartment #4',
    '185 Newark Avenue Jersey City': '185 Newark Avenue Apartment #2',
    '243 Montgomery Street Apartment 4 Jersey City':
        '243 Montgomery Street Apt #4',
    '243 Montgomery Street Apt 2 Jersey City': '243 Montgomery Street Apt #2',
    '243 Montgomery Street Jersey City': '243 Montgomery Street Apt #3',
    'LUXURIOUS 2BR/2BA!! 1 STOP from NYC!! Sleeps 8!! (2834690)':
        '50 Regent Street Apt #409',
    'FABULOUS 2BR/1BA 2 STOPS FROM NYC!! SLEEPS 6!!! (2837358)':
        '50 Regent Street Apt 209',
    '8 Erie Street Jersey City': '8 Erie Street 302',
    '99 Montgomery Street Jersey City': None}


def get_lines():
  return list(csv.reader(open('oldBookingComReservations.csv', 'r')))[1:]


csv_fields = [
    'property_name', 'location', 'booker_name', 'arrival', 'departure',
    'booked_on', 'status', 'total_payment', 'commission', 'reservation_number',
    'cleaning_fee', 'vreasy_payments_total']


class CSVRes(namedtuple('CSVRes', csv_fields)):
  pass


def import_all():
  for line in get_lines():
    reservation_from_csv_res(csv_res_from_line(line))


def reservation_from_line_index(index):
  lines = get_lines()
  csv_res = csv_res_from_line(lines[index])
  return reservation_from_csv_res(csv_res)


def reservation_from_csv_res(csv_res):
  listing = listing_from_csv_res(csv_res)
  if not listing:
    return
  reservation = Reservation.objects.filter(
      channel_reservation_id=csv_res.reservation_number).first()
  if not reservation:
    print('Creating a reservation with id {}'.format(
        csv_res.reservation_number))
    reservation = Reservation(
        channel_reservation_id=csv_res.reservation_number)
  reservation.guest = guest_from_csv_res(csv_res)
  reservation.check_in = date_from_str(csv_res.arrival, 15)
  reservation.check_out = date_from_str(csv_res.departure, 11)
  reservation.night_count = (
      reservation.check_out - reservation.check_in).days
  reservation.booked_at = date_from_str(csv_res.booked_on, 12)
  reservation.listing = listing
  if csv_res.status == 'No-show':
    reservation.status = CANCELED
  elif csv_res.status == 'OK':
    reservation.status = CONFIRMED
  else:
    raise Exception(csv_res.status)
  reservation.save()

  line_items = ReservationLineItem.objects.filter(reservation=reservation)
  line_item = None
  for existing in line_items:
    if KNOWN_LINE_ITEM_NAMES().is_rent(existing.name):
      line_item = existing
  if not line_item:
    print('Creating a line item for {}'.format(csv_res.total_payment))
    line_item = ReservationLineItem(
        name=KNOWN_LINE_ITEM_NAMES.ACCOMMODATION_FARE, reservation=reservation)
  if csv_res.status == 'No-show' and line_item.value != Money(0, 'USD'):
    print('Zeroing out a line item for a canceled reservation.')
    line_item.value = Money(0, 'USD')
  elif csv_res.status == 'OK':
    line_item.value = money_from_str(csv_res.total_payment)
  line_item.save()

  return reservation


def listing_from_csv_res(csv_res):
  rental = rental_from_csv_res(csv_res)
  if not rental:
    return
  listing = Listing.objects.filter(rental=rental, channel=BOOKINGCOM).first()
  if not listing:
    print('Creating a BOOKINGCOM listing for {}'.format(csv_res.location))
    listing = Listing.objects.create(
        rental=rental, channel=BOOKINGCOM, channel_listing_id='???')
  return listing


def guest_from_csv_res(csv_res):
  guest = Guest.objects.filter(full_name=csv_res.booker_name).first()
  if not guest:
    full_name = csv_res.booker_name
    print('Creating guest {}'.format(full_name))
    name_parts = full_name.split(' ')
    guest = Guest.objects.create(
        full_name=full_name, first_name=name_parts[0],
        phone='???-???-????')
  return guest


def rental_from_csv_res(csv_res):
  if csv_res.property_name in LOCATION_LOOKUP:
    location = LOCATION_LOOKUP[csv_res.property_name]
  else:
    location = LOCATION_LOOKUP[csv_res.location]
  if location:
    return Rental.objects.get(airbnb_address_scrape__contains=location)


def csv_res_from_line(line):
  return CSVRes(*line)


def get_distinct(column_index):
  distinct = set()
  for line in get_lines():
    distinct.add(line[column_index])
  return list(sorted(list(distinct)))


def date_from_str(date_str, hour):
  # date_str is, like, '23 September 2017'
  dt = datetime.strptime(date_str, '%d %B %Y')
  return make_aware(datetime(
      year=dt.year, month=dt.month, day=dt.day, hour=hour))


def money_from_str(money_str):
  # money_str is, like, 'US$1,147.50'
  return Money(float(re.sub(r'[^\.\d]', '', money_str)), 'USD')
