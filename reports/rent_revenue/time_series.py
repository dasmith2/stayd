from calendar import monthrange
from collections import namedtuple

from reports.rent_revenue.util import (
    reservations_in_range, single_day_res_stats)


DAY = 'day'
WEEK = 'week'
MONTH = 'month'
INTERVALS = (DAY, WEEK, MONTH)


class Point(namedtuple('Point', 'from_date interval res_stats')):
  pass


class TimeSeries(object):
  def get_points(self, from_date, to_date, interval, city=None):
    lookup = self._get_points_lookup(from_date, to_date, interval, city)
    reservations = reservations_in_range(self.from_date, self.to_date)
    if city:
      reservations = reservations.filter(__rental__city=city)
    for reservation in reservations:
      single_day = single_day_res_stats(
          reservation, self.from_date, self.to_date)
      on = reservation.check_in.date()
      end = reservation.check_out.date()
      while on < end:
        key_date = self._get_key_date_from_key(on)
        if key_date in lookup:
          lookup[key_date].res_stats.add(single_day)
        on += timedelta(days=1)
    return list(sorted(lookup.values(), key=lambda x: x.from_date))

  def _get_rental_count(self, city):
    rentals = Rental.objects.filter(is_active=True)
    if city:
      rentals = rentals.filter(city=city)
    return rentals.count()

  def _get_points_lookup(self, from_date, to_date, interval, city):
    lookup = {}
    on = from_date
    rental_count = self._get_rental_count(city)
    while on < to_date:
      key_date = self._get_key_date_from_key(on)
      if key_date not in lookup and key_date >= from_date:
        lookup[key_date] = Point(
            from_date=key_date, interval=interval,
            res_stats=ResStats())
        max_occupancy = 0
        if interval == DAY:
          max_occupancy = 1
        elif interval == WEEK:
          max_occupancy = 7
        elif interval == MONTH:
          max_occupancy = monthrange(key_date.year, key_date.month)
        max_occupancy *= rental_count
        lookup[key_date].res_stats.max_occupancy = max_occupancy

  def _get_key_date_from_key(self, on):
    if self.interval == DAY:
      return on
    elif self.interval == WEEK:
      # Monday == 0, Sunday == 6
      if on.weekday == 6:
        return on
      return on - timedelta(days=on.weekday() + 1)
    elif self.interval == MONTH:
      return on.replace(day=1)
    else:
      raise Exception(self.interval)
