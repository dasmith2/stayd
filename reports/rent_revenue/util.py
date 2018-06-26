from datetime import timedelta
from pytz import timezone

from djmoney.money import Money

from errors.models import log_error
from reservations.models import Reservation, KNOWN_LINE_ITEM_NAMES, CONFIRMED
from util.channels import BOOKINGCOM
from util.timezone import midnight_from_date


DAY = 'day'
WEEK = 'week'
MONTH = 'month'
INTERVALS = (DAY, WEEK, MONTH)


class ResStats(object):
  """ Pretty basic object here for keeping track of rent, revenue, fees,
  max_occupancy available, and occupied days.

  Assumption: Everything is USD all the time! """
  def __init__(
      self, total_charges=Money(0, 'USD'), cleaning_fees=Money(0, 'USD'),
      channel_fees=Money(0, 'USD'), taxes=Money(0, 'USD'),
      rent=Money(0, 'USD')):
    self.total_charges = total_charges
    self.cleaning_fees = cleaning_fees
    self.channel_fees = channel_fees
    self.taxes = taxes
    self.rent = rent
    # The theoretical maximum number of bookable nights.
    self.max_occupancy = 0
    # How many nights actually got booked.
    self.occupied_days = 0

  def add(self, res_stats):
    self.total_charges += res_stats.total_charges
    self.cleaning_fees += res_stats.cleaning_fees
    self.channel_fees += res_stats.channel_fees
    self.taxes += res_stats.taxes
    self.rent += res_stats.rent
    self.max_occupancy += res_stats.max_occupancy
    self.occupied_days += res_stats.occupied_days

  def multiply(self, fraction):
    self.total_charges *= fraction
    self.cleaning_fees *= fraction
    self.channel_fees *= fraction
    self.taxes *= fraction
    self.rent *= fraction
    self.max_occupancy *= fraction
    self.occupied_days = round(self.occupied_days * fraction)

  def total_expenses(self):
    return self.rent + self.cleaning_fees + self.channel_fees + self.taxes

  def net(self):
    return self.total_charges - self.total_expenses()

  def adr(self):
    """ Average daily rate. It's the average income from occupied nights. """
    if not self.occupied_days:
      if self.total_charges:
        raise Exception('How do I have charges without any occupied nights?')
      return Money(0.0, 'USD')
    return self.total_charges / self.occupied_days

  def occupancy_rate(self):
    """ Percent of nights with somebody in the apartments compared to total
    nights available in the apartments, expressed as a percentage. """
    if self.max_occupancy:
      return int(100.0 * self.occupied_days / self.max_occupancy)
    return 0

  def rev_par(self):
    """ Average revenue per available room per night. Another way to calculate
    this is by multiplying the adr by the occupancy rate. """
    if self.max_occupancy:
      return self.total_charges / self.max_occupancy
    return Money(0.0, 'USD')


def _total_days_and_within_from_to(reservation, from_date, to_date):
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


def reservations_in_range(from_date, to_date, owner_id=None):
  """ Due to timezones, pull back potentially too many reservations and let
  _total_days_and_within_from_to do the work of figuring out if that
  reservation is ACTUALLY in the right time.
  This is one of the only actually smart parts in this whole thing.
  Draw timelines to see how it works. """
  search_check_in = midnight_from_date(to_date) + timedelta(days=1)
  search_check_out = midnight_from_date(from_date) - timedelta(days=1)
  reservations = Reservation.objects.filter(
      status=CONFIRMED,
      check_in__lte=search_check_in,
      check_out__gte=search_check_out,
      listing__rental__is_active=True).select_related(
          'listing', 'listing__rental', 'guest').order_by('check_in')
  if owner_id:
    reservations = reservations.filter(listing__rental__owner__pk=owner_id)
  return reservations


def pro_rated_res_stats(reservation, from_date, to_date):
  """ How much of charges, occupied days, etc... for a reservation can be
  attributed to happening in the given date range, given the check in
  and check out of the reservation? """
  res_stats = reservation_res_stats(reservation)
  (total_reservation_days, within) = _total_days_and_within_from_to(
      reservation, from_date, to_date)
  fraction = 1.0 * within / total_reservation_days
  res_stats.multiply(fraction)
  return res_stats


def single_day_res_stats(reservation):
  """ How much of charges, occupied days, etc... for a reservation can be
  attributed to a single day out of that reservation? Well, occupied days
  should always be 1 in this case. """
  res_stats = reservation_res_stats(reservation)
  fraction = 1.0 / res_stats.occupied_days
  res_stats.multiply(fraction)
  return res_stats


def reservation_res_stats(reservation):
  """ Return the total charges, occupied days, and so on for a reservation. """
  res_stats = ResStats()
  accommodation_cost = Money(0, 'USD')
  line_items = reservation.line_items()
  if line_items:
    names = KNOWN_LINE_ITEM_NAMES()
    # Typical example: $1262 accommodation fare, $100 cleaning fee,
    # $-40.86 Host channel fee. Then the host payout will be $1321.14.
    # But $100 of that goes straight to cleaners. So revenue is $1221.14.
    for line_item in line_items:
      # Channel fees are negative and get taken out of the revenue from the
      # room itself. In other words, they're don't affect the total charges
      # for the guest. They only affect our bottom line. For booking.com
      # reservations, these channel fees are so high we change the
      # nightly rate to make up for it.
      if names.is_channel_fee(line_item.name):
        res_stats.channel_fees -= line_item.value
      elif names.is_cleaning(line_item.name):
        res_stats.cleaning_fees += line_item.value
        res_stats.total_charges += line_item.value
      elif names.is_rent_or_correction(line_item.name):
        accommodation_cost += line_item.value
        res_stats.total_charges += line_item.value
      elif names.is_tax(line_item.name):
        res_stats.taxes += line_item.value
        res_stats.total_charges += line_item.value
      else:
        log_error(
            'What do I do with {} line items?'.format(line_item.name),
            'reservation {}'.format(reservation.pk))
  if reservation.listing.channel == BOOKINGCOM:
    # Booking.com bills us 15% of the room rate due at the end of the month,
    # so their channel fee isn't in the line items.
    bookingcom_fee = .15 * accommodation_cost
    res_stats.channel_fees += bookingcom_fee

  res_stats.occupied_days = (
      reservation.check_out.date() - reservation.check_in.date()).days
  return res_stats
