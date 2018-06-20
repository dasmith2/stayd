from calendar import monthrange
from datetime import timedelta

from rentals.models import Rental
from reports.rent_revenue.util import (
    reservations_in_range, single_day_res_stats, DAY, WEEK, MONTH,
    ResStats)


class Point(ResStats):
  def __init__(self, from_date, interval):
    self.from_date = from_date
    self.interval = interval
    super(Point, self).__init__()

  def get_label(self):
    return self.from_date.strftime('%b %d')


def get_points(from_date, to_date, interval, city=None):
  lookup = _get_points_lookup(from_date, to_date, interval, city)
  reservations = reservations_in_range(from_date, to_date)
  if city:
    reservations = reservations.filter(listing__rental__city=city)
  for reservation in reservations:
    single_day = single_day_res_stats(reservation)
    on = reservation.check_in.date()
    end = reservation.check_out.date()
    while on < end:
      key_date = _get_key_date_from_key(on, interval)
      if key_date in lookup:
        lookup[key_date].add(single_day)
      on += timedelta(days=1)
  return list(sorted(lookup.values(), key=lambda x: x.from_date))


def _get_points_lookup(from_date, to_date, interval, city):
  lookup = {}
  on = from_date
  rental_count = _get_rental_count(city)
  while on < to_date:
    key_date = _get_key_date_from_key(on, interval)
    if key_date not in lookup and key_date >= from_date:
      lookup[key_date] = Point(from_date=key_date, interval=interval)
      max_occupancy = 0
      if interval == DAY:
        max_occupancy = 1
      elif interval == WEEK:
        max_occupancy = 7
      elif interval == MONTH:
        max_occupancy = monthrange(key_date.year, key_date.month)
      max_occupancy *= rental_count
      lookup[key_date].max_occupancy = max_occupancy
    on += timedelta(days=1)
  return lookup


def _get_rental_count(city):
  rentals = Rental.objects.filter(is_active=True)
  if city:
    rentals = rentals.filter(city=city)
  return rentals.count()


def _get_key_date_from_key(on, interval):
  if interval == DAY:
    return on
  elif interval == WEEK:
    # Monday == 0, Sunday == 6
    if on.weekday == 6:
      return on
    return on - timedelta(days=on.weekday() + 1)
  elif interval == MONTH:
    return on.replace(day=1)
  else:
    raise Exception(interval)
