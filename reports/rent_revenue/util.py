from collections import namedtuple
from datetime import timedelta
from pytz import timezone

from djmoney.money import Money

from errors.models import log_error
from reservations.models import Reservation, KNOWN_LINE_ITEM_NAMES, CONFIRMED
from util.channels import BOOKINGCOM
from util.timezone import midnight_from_date


def total_days_and_within_from_to(reservation, from_date, to_date):
  """ This is a little tricky. People check out on one day and then somebody
  new checks in on the same day. So a reservation counts as being on a day
  if you're staying through that night. If you checkin on the 15th and out on
  the 16th, 100% of the revenue counts towards the 15th. to_date is exclusive,
  so querying from the 15th to the 15th will always return 0. So if you want
  to know about January, query from January 1st to February 1st, which if you
  think about it, is the checkout day and doesn't count towards revenue.

  This computes based on the timezone of the rental, so if you query for
  Tuesday you'll get this reservation's rental's understanding of Tuesday,
  not some global understaind of Tuesday. """
  tzinfo = timezone(reservation.listing.rental.time_zone)
  from_dt = midnight_from_date(from_date, tzinfo)
  to_dt = midnight_from_date(to_date, tzinfo)
  within = 0
  total_days = 0
  on = reservation.get_check_in()
  check_out = reservation.get_check_out()
  while on < check_out:
    total_days += 1
    if from_dt <= on and on <= to_dt:
      within += 1
    on += timedelta(days=1)
  return (total_days, within)


def reservations_in_range(from_date, to_date):
  """ Due to timezones, pull back potentially too many reservations and let
  total_days_and_within_from_to do the work of figuring out if that
  reservation is ACTUALLY in the right time.
  This is one of the only actually smart parts in this whole thing.
  Draw timelines to see how it works. """
  search_check_in = midnight_from_date(to_date) + timedelta(days=1)
  search_check_out = midnight_from_date(from_date) - timedelta(days=1)
  return Reservation.objects.filter(
      status=CONFIRMED,
      check_in__lte=search_check_in,
      check_out__gte=search_check_out,
      listing__rental__is_active=True).select_related(
          'listing', 'listing__rental', 'guest').order_by('check_in')


class ChargesAndFees(namedtuple(
    'ChargesAndFees', 'total_charges cleaning_fee channel_fee')):
  pass


def pro_rated_charges_and_fees(charges_and_fees, fraction):
  # This might be a little too cute...
  return ChargesAndFees(*(caf * fraction for caf in charges_and_fees))


def reservation_charges_and_fees(reservation):
  """ Still missing from this due to never seeing an example yet,
  we add a service fee for Booking.com that should come in as a
  line item. That should be added into the amount. """
  total_charges = Money(0, 'USD')
  cleaning_fee = Money(0, 'USD')
  channel_fee = Money(0, 'USD')
  accommodation_cost = Money(0, 'USD')
  line_items = reservation.line_items()
  if line_items:
    names = KNOWN_LINE_ITEM_NAMES()
    # Typical example: $1262 accommodation fare, $100 cleaning fee,
    # $-40.86 Host channel fee. Then the host payout will be $1321.14.
    # But $100 of that goes straight to cleaners. So revenue is $1221.14.
    for line_item in line_items:
      # Channel fees are negative and get taken out of the revenue from the
      # room itself.
      if names.is_channel_fee(line_item.name):
        channel_fee -= line_item.value
      elif names.is_cleaning(line_item.name):
        cleaning_fee += line_item.value
        total_charges += line_item.value
      elif names.is_rent_or_correction(line_item.name):
        accommodation_cost += line_item.value
        total_charges += line_item.value
      elif names.is_tax(line_item.name):
        log_error(
            'Found a reservation with taxes', (
                'Check it out for the rent_revenue report, specifically '
                'reservation_charges_and_fees. pk {}'.format(reservation.pk)))
      else:
        log_error(
            'What do I do with {} line items?'.format(line_item.name),
            'reservation {}'.format(reservation.pk))
  if reservation.listing.channel == BOOKINGCOM:
    # Booking.com bills us 15% of the room rate due at the end of the month,
    # so their channel fee isn't in the line items.
    bookingcom_fee = .15 * accommodation_cost
    channel_fee += bookingcom_fee
  return ChargesAndFees(
      total_charges=total_charges,
      cleaning_fee=cleaning_fee,
      channel_fee=channel_fee)
