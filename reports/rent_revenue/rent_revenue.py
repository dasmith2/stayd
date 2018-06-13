from calendar import monthrange
from collections import namedtuple
from datetime import timedelta
from pytz import timezone

from djmoney.money import Money

from errors.models import log_error
from rentals.models import Rental
from reservations.models import Reservation, KNOWN_LINE_ITEM_NAMES
from util.channels import BOOKINGCOM
from util.timezone import midnight_from_date


class RentRevenue(object):
  """ Pretty basic object here for keeping track of rent and revenue
  for something, be it a single rental or a whole city. """
  def __init__(self, name, indent, city=''):
    self.name = name
    self.indent = indent
    self.city = city or name
    # Assumption: Everything is USD all the time!
    self.rent = Money(0, 'USD')
    self.revenue = Money(0, 'USD')
    self.total_charges = Money(0, 'USD')
    self.cleaning_fees = Money(0, 'USD')
    self.channel_fees = Money(0, 'USD')
    self.days = 0
    self.occupied_days = 0

  def add_rent(self, rent):
    self.rent += rent

  def add_line_items(self, line_items):
    self.revenue += line_items.revenue
    self.total_charges += line_items.total_charges
    self.cleaning_fees += line_items.cleaning_fee
    self.channel_fees += line_items.channel_fee

  def add_days(self, days):
    self.days += days

  def add_occupied_days(self, occupied_days):
    self.occupied_days += occupied_days

  def adr(self):
    """ Average daily rate. It's the average income from occupied nights. """
    if not self.occupied_days:
      if self.revenue:
        raise Exception('How do I have revenue without any occupied nights?')
      return 0.0
    return self.revenue / self.occupied_days

  def occupancy_rate(self):
    """ Percent of nights with somebody in the apartments compared to total
    nights available in the apartments, expressed as a percentage. """
    return int(100.0 * self.occupied_days / self.days)

  def rev_par(self):
    """ Average revenue per available room per night. Another way to calculate
    this is by multiplying the adr by the occupancy rate. """
    return self.revenue / self.days

  def __repr__(self):
    return 'RentRevenue({}, {}, {})'.format(self.name, self.indent, self.city)


def get_rent_revenues(from_date, to_date):
  """ to_date is exclusive. So if you want to query about march you do
  3/1/2018 through 4/1/2018. Note that this is different from the user
  interface, and that the view adds a day to to_date, making the user
  interface to_date inclusive. So in the user interface you'd do
  3/1/2018 through 3/.../2018 see I'm not even sure. How many days are in
  March? But with the calendar it's easy. You just pick the last day of
  the month. """
  total = RentRevenue('Total', 0)
  by_city = {}
  by_rental = {}

  _add_rents_and_total_days(from_date, to_date, total, by_city, by_rental)

  _add_revenue_and_occupied_days(from_date, to_date, total, by_city, by_rental)

  return _merge_rent_revenues(total, by_city, by_rental)


def _add_rents_and_total_days(from_date, to_date, total, by_city, by_rental):
  """ This is the reservation agnostic stuff, the potential days to fill and
  the overhead. This is the space we're working in. """
  months = pro_rated_month_count(from_date, to_date)
  total_days = days_in_range(from_date, to_date)
  for rental in Rental.objects.filter(is_active=True):
    pro_rated_rent = rental.market_rent * months
    total.add_rent(pro_rated_rent)
    city = rental.city
    if city not in by_city:
      by_city[city] = RentRevenue(city, 1, city)
    by_city[city].add_rent(pro_rated_rent)
    nickname = rental.get_nickname()
    if nickname not in by_rental:
      by_rental[nickname] = RentRevenue(nickname, 2, city)
    by_rental[nickname].add_rent(pro_rated_rent)

    total.add_days(total_days)
    by_city[city].add_days(total_days)
    by_rental[nickname].add_days(total_days)


def _add_revenue_and_occupied_days(
    from_date, to_date, total, by_city, by_rental):
  """ This is the stuff that depends on reservations. This is what we
  accomplished. """
  # Due to timezones, pull back potentially too many reservations and let
  # total_days_and_within_from_to do the work of figuring out if that
  # reservation is ACTUALLY in the right time.
  search_check_in = midnight_from_date(to_date) + timedelta(days=1)
  search_check_out = midnight_from_date(from_date) - timedelta(days=1)
  # This is one of the only actually smart parts in this whole thing.
  # Draw timelines to see how it works.
  reservations = Reservation.objects.filter(
      check_in__lte=search_check_in,
      check_out__gte=search_check_out,
      listing__rental__is_active=True).select_related(
          'listing', 'listing__rental')
  for reservation in reservations:
    (total_reservation_days, within) = total_days_and_within_from_to(
        reservation, from_date, to_date)
    fraction = 1.0 * within / total_reservation_days

    line_items = reservation_revenue(reservation)
    # This might be a little too cute...
    pro_rated_line_items = LineItems(*(li * fraction for li in line_items))

    total.add_line_items(pro_rated_line_items)
    total.add_occupied_days(within)
    city = reservation.listing.rental.city
    by_city[city].add_line_items(pro_rated_line_items)
    by_city[city].add_occupied_days(within)
    nickname = reservation.listing.rental.get_nickname()
    by_rental[nickname].add_line_items(pro_rated_line_items)
    by_rental[nickname].add_occupied_days(within)


def _merge_rent_revenues(total, by_city, by_rental):
  rent_revenues = [total]

  cities = sorted(by_city.values(), key=lambda rr: rr.city)
  rentals = sorted(by_rental.values(), key=lambda rr: rr.city + rr.name)
  on_rental = 0
  for city in cities:
    rent_revenues.append(city)
    while on_rental < len(rentals) and rentals[on_rental].city == city.city:
      rent_revenues.append(rentals[on_rental])
      on_rental += 1
  if on_rental != len(rentals):
    log_error(
        'Error merging rentals with cities in the rent and revenue report',
        'cities: {}\n\nrentals: {}'.format(cities, rentals))
  return rent_revenues


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


class LineItems(namedtuple(
    'LineItems', 'total_charges cleaning_fee channel_fee revenue')):
  pass


def reservation_revenue(reservation):
  """ Still missing from this due to never seeing an example yet,
  we add a service fee for Booking.com that should come in as a
  line item. That should be added into the amount. """
  total_charges = Money(0, 'USD')
  cleaning_fee = Money(0, 'USD')
  channel_fee = Money(0, 'USD')
  revenue = Money(0, 'USD')
  line_items = reservation.line_items()
  if not line_items:
    log_error(
        'Reservation has no line items',
        'Reservation {}. I\'m using the total_payin as a standin for '
        'now, but this is inaccurate.'.format(reservation.pk))
    revenue = reservation.total_payin
  else:
    names = KNOWN_LINE_ITEM_NAMES()
    # Typical example: $1262 accommodation fare, $100 cleaning fee,
    # $-40.86 Host channel fee. Then the host payout will be $1321.14.
    # But $100 of that goes straight to cleaners. So revenue is $1221.14.
    for line_item in line_items:
      # Channel fees are negative and get taken out of the revenue from the
      # room itself.
      if names.is_channel_fee(line_item.name):
        revenue += line_item.value
        channel_fee -= line_item.value
      elif names.is_cleaning(line_item.name):
        cleaning_fee += line_item.value
        total_charges += line_item.value
      elif names.is_rent_or_correction(line_item.name):
        revenue += line_item.value
        total_charges += line_item.value
      elif names.is_tax(line_item.name):
        # TODO, figure out what to do with this.
        pass
      else:
        log_error(
            'What do I do with {} line items?'.format(line_item.name),
            'reservation {}'.format(reservation.pk))
  if reservation.listing.channel == BOOKINGCOM:
    # Booking.com bills us 15% at the end of the month, so their channel
    # fee isn't in the line items. The booking.com service fee is meant
    # to balance this out.
    bookingcom_fee = .15 * revenue
    channel_fee += bookingcom_fee
    revenue -= bookingcom_fee
  return LineItems(
      total_charges=total_charges,
      cleaning_fee=cleaning_fee,
      channel_fee=channel_fee,
      revenue=revenue)


def days_in_range(from_date, to_date):
  """ to_date is exclusive. """
  on = from_date
  total_days = 0
  while on < to_date:
    total_days += 1
    on += timedelta(days=1)
  return total_days


def pro_rated_month_count(from_date, to_date):
  """ How much, like, month-age is in the date range as expressed as a
  decimal? So 1/15/2018 - 3/1/2018 would return something like 1.5
  to_date is exclusive. """
  months = {}
  on = from_date
  while on < to_date:
    key = (on.year, on.month)
    if key not in months:
      months[key] = 1
    else:
      months[key] += 1
    on += timedelta(days=1)
  total_months = 0.0
  for month, days_in_month in months.items():
    total_days_in_month = monthrange(*month)[1]
    total_months += 1.0 * days_in_month / total_days_in_month
  return total_months
