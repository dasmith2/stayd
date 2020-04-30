""" If you wanna retrieve day by day stats for an owner, say, that's pretty
easy. Just pull the owner day stats from the database for the date range in
order and return them. It's possible that the date range in question is before
units were available or whatever, in which case just fill in the gaps with
blank Stats.  If you want total stats for a time span, then you pull back a few
day and month stats who add up to the time span, and then add them all together
and return that Stats.

Getter is blissfully unaware of what all the exact stats are. """
from datetime import timedelta

from django.contrib.auth.models import User

from rentals.models import Building, Rental
from stats.models.stats import Stats, DAY, WEEK, MONTH, TOTAL
from util.timezone import add_months


class StatsGetter(object):
  def get_stats(
      self, from_date, to_date, interval, owner_id=None, building_id=None,
      rental_id=None):
    """ This is for when you have a specific entity in mind and you want a
    gapless time series. If what you want is just all the MONTH stats, just
    query the Stats object directly.

    If you don't specify owner_id, building_id, or rental_id, this thinks
    you're asking about the entire business added together. If you specify DAY,
    WEEK, or MONTH, it'll fill in the gaps. So if you do get_stats(date(2018,
    1, 1), date(2019, 1, 1), MONTH) it'll return 12 Stats objects to you
    representing ALL the business. """
    if from_date > to_date:
      raise Exception('from_date should be less than to_date.')
    if interval == MONTH and (from_date.day != 1 or to_date.day != 1):
      raise Exception((
          'If youre querying by month, the from_date and to_date should be on '
          'the first of the month. Theyre {} and {} '
          'respectively').format(from_date, to_date))
    if interval == WEEK and (
        from_date.weekday() != 6 or to_date.weekday() != 6):
      raise Exception((
          'If youre querying by week, the from_date and to_date should be on '
          'Sundays a.k.a. 6. Theyre on {} and {} respectively.').format(
              from_date.weekday(), to_date.weekday()))
    # Sorry, hope this isn't too magic. int(True) == 1, and int(False) == 0
    if int(bool(owner_id)) + int(bool(building_id)) + int(
        bool(rental_id)) > 1:
      raise Exception((
          'Specify at most one of owner_id {}, building_id {}, and '
          'rental_id {}').format(owner_id, building_id, rental_id))

    rental = None
    building = None
    owner = None
    # If there's a specific building, Owner is redundant and should be left out
    # of the call to _get_statses.
    if rental_id:
      rental = Rental.objects.get(pk=rental_id)
    elif building_id:
      building = Building.objects.get(pk=building_id)
    elif owner_id:
      owner = User.objects.get(pk=owner_id)
    if interval in (DAY, WEEK, MONTH):
      statses = self._get_statses(
          from_date, to_date, interval, rental, building, owner)
      return self._fill_in_gaps(statses, from_date, to_date, interval)
    elif interval == TOTAL:
      return self._get_total(from_date, to_date, rental, building, owner)
    else:
      raise Exception(interval)

  def _get_statses(
      self, from_date, to_date, search_interval, rental, building, owner):
    statses = Stats.objects.filter(
        interval=search_interval, from_date__gte=from_date,
        from_date__lt=to_date).select_related(
            'rental', 'rental__building', 'building')
    if rental or building or owner:
      return statses.filter(rental=rental, building=building, owner=owner)
    else:
      to_return = []
      for stats in statses.filter(owner__isnull=False):
        if to_return and to_return[-1].from_date == stats.from_date:
          to_return[-1].add(stats)
        else:
          stats.pk = None
          stats.owner = None
          to_return.append(stats)
      return to_return

  def _get_total(self, from_date, to_date, rental, building, owner):
    if from_date >= to_date:
      return Stats()
    statses = self._get_statses(
        from_date, to_date, DAY, rental, building, owner)
    return self.sum_statses(statses, from_date)

  def sum_statses(self, statses, from_date=None):
    total = Stats(interval=TOTAL, from_date=from_date)
    for stats in statses:
      total.add(stats)
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
    elif interval == WEEK:
      return on_date + timedelta(days=7)
    elif interval == MONTH:
      return add_months(on_date, 1)
    else:
      raise Exception(interval)
