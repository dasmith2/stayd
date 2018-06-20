from calendar import monthrange
from datetime import timedelta

from django.urls import reverse

from errors.models import log_error
from rentals.models import Rental
from reports.rent_revenue.util import (
    reservations_in_range, pro_rated_res_stats, ResStats)
from util.url_date import date_to_url_str


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
    total.rent += pro_rated_rent
    city = rental.city
    if city not in by_city:
      by_city[city] = RentRevenue(city, 1, city)
    by_city[city].rent += pro_rated_rent
    nickname = rental.get_nickname()
    if nickname not in by_rental:
      by_rental[nickname] = RentRevenue(nickname, 2, city)
      by_rental[nickname].url = reverse('reservation_list', kwargs={
          'rental_id': rental.pk,
          'from_date_str': date_to_url_str(from_date),
          'to_date_str': date_to_url_str(to_date)})
    by_rental[nickname].rent += pro_rated_rent

    total.max_occupancy += total_days
    by_city[city].max_occupancy += total_days
    by_rental[nickname].max_occupancy += total_days


def _add_revenue_and_occupied_days(
    from_date, to_date, total, by_city, by_rental):
  """ This is the stuff that depends on reservations. This is what we
  accomplished. """
  for reservation in reservations_in_range(from_date, to_date):
    pro_rated = pro_rated_res_stats(reservation, from_date, to_date)

    total.add(pro_rated)
    by_city[reservation.listing.rental.city].add(pro_rated)
    by_rental[reservation.listing.rental.get_nickname()].add(pro_rated)


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


class RentRevenue(ResStats):
  """ This keeps track of rent and revenue for something, be it a single rental
  or a whole city. It also includes some display information suitable for
  the rent revenue report. """
  def __init__(self, name, indent, city=''):
    super(RentRevenue, self).__init__()
    self.name = name
    self.indent = indent
    self.city = city or name
    self.url = None

  def __repr__(self):
    return 'RentRevenue({}, {}, {})'.format(self.name, self.indent, self.city)
