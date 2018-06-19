from collections import namedtuple

from reports.rent_revenue.util import (
    reservations_in_range, single_day_res_stats)


DAY = 'day'
WEEK = 'week'
MONTH = 'month'
INTERVALS = (DAY, WEEK, MONTH)


class Point(namedtuple('Point', 'start_date interval res_stats')):
  pass


class TimeSeries(object):
  def __init__(self, start_date, end_date, interval):
    self.start_date = start_date
    self.end_date = end_date
    self.interval = interval

  def get_points(self, city=None):
    reservations = reservations_in_range(self.start_date, self.end_date)
    for reservation in reservations:
      pro_rated = single_day_res_stats(
          reservation, self.start_date, self.end_date)
      on = reservation.check_in.date()
      end = reservation.check_out.date()

  def _get_points_lookup(self):
    lookup = {}
    on = self.start_date
    while on < self.end_date:
      lookup[on] = Point(start_date=on)
