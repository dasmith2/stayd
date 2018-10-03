""" If you wanna retrieve day by day stats for an owner, say, that's pretty
easy. Just pull the owner day stats from the database for the date range in
order and return them. It's possible that the date range in question is before
units were available or whatever, in which case just fill in the gaps with
blank Stats.  If you want total stats for a time span, then you pull back a few
day and month stats who add up to the time span, and then add them all together
and return that Stats.

Getter is blissfully unaware of what all the exact stats are. """
from datetime import date, timedelta

from django.contrib.auth.models import User

from rentals.models import Building
from stats.models.stats import Stats, DAY, MONTH, TOTAL
from util.timezone import add_months


class StatsGetter(object):
  """ Assuming the stats are all up to date in the database, StatsGetter knows
  how to retrieve totals and time series from the database. """
  def get_stats(
      self, from_date, to_date, interval, owner_id=None, building_id=None):
    if from_date > to_date:
      raise Exception('from_date should be less than to_date.')
    if interval == MONTH and (from_date.day != 1 or to_date.day != 1):
      raise Exception((
          'If youre querying by month, the from_date and to_date should be on '
          'the first of the month. Theyre {} and {} '
          'respectively').format(from_date, to_date))

    building = None
    owner = None
    # If there's a specific building, Owner is redundant and should be left out
    # of the call to _get_statses.
    if building_id:
      building = Building.objects.get(pk=building_id)
    elif owner_id:
      owner = User.objects.get(pk=owner_id)
    else:
      raise Exception(
          'You should specify a building id or an owner id')
    if interval in (DAY, MONTH):
      statses = self._get_statses(
          interval, from_date, to_date, building, owner)
      return self._fill_in_gaps(statses, from_date, to_date, interval)
    elif interval == TOTAL:
      return self._get_total(from_date, to_date, building, owner)
    else:
      raise Exception(interval)

  def _get_statses(
      self, search_interval, from_date, to_date, building, owner):
    return Stats.objects.filter(
        interval=search_interval, from_date__gte=from_date,
        from_date__lt=to_date, building=building, owner=owner)

  def _get_total(self, from_date, to_date, building, owner):
      whole_months_start = from_date
      days_before = Stats()
      if from_date.day != 1:
        whole_months_start = add_months(
            date(from_date.year, from_date.month, 1), 1)
        days_before = self._get_interval_total(
            DAY, from_date, whole_months_start, building, owner)

      whole_months_end = to_date
      days_after = Stats()
      if to_date.day != 1:
        whole_months_end = date(to_date.year, to_date.month, 1)
        days_after = self._get_interval_total(
            DAY, whole_months_end, to_date, building, owner)

      whole_months = self._get_interval_total(
          MONTH, whole_months_start, whole_months_end, building, owner)

      return self.sum_statses(
          [days_before, whole_months, days_after], from_date)

  def sum_statses(self, statses, from_date=None):
    total = Stats(interval=TOTAL, from_date=from_date)
    for stats in statses:
      total.add(stats)
    return total

  def _get_interval_total(
      self, interval, from_date, to_date, building, owner):
    if from_date >= to_date:
      return Stats()
    return self.sum_statses(
        self._get_statses(interval, from_date, to_date, building, owner),
        from_date)

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
