from datetime import date, timedelta

from django.contrib.auth.models import User

from rentals.models import Rental
from stats.models.stats import Stats, DAY, MONTH, TOTAL
from util.timezone import add_months


class StatsGetter(object):
  """ Assuming the stats are all up to date in the database, StatsGetter knows
  how to retrieve totals and time series from the database. """
  def get_stats(
      self, from_date, to_date, interval, city=None, rental_id=None,
      owner_id=None):
    rental = None
    owner = None
    # If there's a specific rental, Owner and city are redundant and should be
    # None.
    if rental_id:
      rental = Rental.objects.get(pk=rental_id)
      city = None
    elif owner_id:
      owner = User.objects.get(pk=owner_id)
    elif city:
      raise Exception('If there\'s a city, there must also be an owner.')
    else:
      raise Exception(
          'You should specify a rental id, or an owner id, or a city and an '
          'owner id.')
    if interval in (DAY, MONTH):
      statses = self._get_statses(
          interval, from_date, to_date, city, rental, owner)
      return self._fill_in_gaps(statses, from_date, to_date, interval)
    elif interval == TOTAL:
      return self._get_total(from_date, to_date, city, rental, owner)
    else:
      raise Exception(interval)

  def _get_statses(
      self, search_interval, from_date, to_date, city, rental, owner):
    return Stats.objects.filter(
        interval=search_interval, from_date__gte=from_date,
        from_date__lt=to_date, city=city, rental=rental, owner=owner)

  def _get_total(self, from_date, to_date, city, rental, owner):
      whole_months_start = from_date
      days_before = Stats()
      if from_date.day != 1:
        whole_months_start = add_months(
            date(from_date.year, from_date.month, 1), 1)
        days_before = self._get_interval_total(
            DAY, from_date, whole_months_start, city, rental, owner)

      whole_months_end = to_date
      days_after = Stats()
      if to_date.day != 1:
        whole_months_end = date(to_date.year, to_date.month, 1)
        days_after = self._get_interval_total(
            DAY, whole_months_end, to_date, city, rental, owner)

      whole_months = self._get_interval_total(
          MONTH, whole_months_start, whole_months_end, city, rental, owner)

      return self._sum_statses(
          [days_before, whole_months, days_after], from_date)

  def _get_interval_total(
      self, interval, from_date, to_date, city, rental, owner):
    if from_date >= to_date:
      return Stats()
    return self._sum_statses(
        self._get_statses(interval, from_date, to_date, city, rental, owner),
        from_date)

  def _sum_statses(self, statses, from_date):
    total = Stats(interval=TOTAL, from_date=from_date)
    for stats in statses:
      total._add(stats)
    return total

  def _fill_in_gaps(self, statses, from_date, to_date, interval):
    on_date = from_date
    to_return = []
    for stats in statses:
      while on_date < stats.from_date:
        to_return.append(Stats(from_date=on_date, interval=interval))
        on_date = self._increment(on_date, interval)
      if on_date > stats.from_date:
        raise Exception(
            'How did on_date {} overtake stats.from_date {}?'.format(
                on_date, stats.from_date))
      to_return.append(stats)
      on_date = self._increment(on_date, interval)
    while on_date < to_date:
      to_return.append(Stats(from_date=on_date, interval=interval))
      on_date = self._increment(on_date, interval)
    return to_return

  def _increment(self, on_date, interval):
    if interval == DAY:
      return on_date + timedelta(days=1)
    elif interval == MONTH:
      return add_months(on_date, 1)
    else:
      raise Exception(interval)
