from django.db.models import Count

from rentals.models import Building
from stats.models.getter import StatsGetter
from stats.models.stats import MONTH, TOTAL
from util.timezone import add_months


class MonthTotals(object):
  """ Exactly the fields that the chart on the dashboard homepage needs. income
  expenses and profit that are in the bank, those that are booked in the near
  future, and a fairly stupid guess at projected profit. """
  def __init__(self, from_date, past_stats, booked_stats):
    self.from_date = from_date
    self.projected_income = None
    if past_stats:
      self.past_income = past_stats.total_income()
      self.past_expenses = past_stats.total_expenses()
      self.past_profit = past_stats.net()
    else:
      self.past_income = None
      self.past_expenses = None
      self.past_profit = None
    if booked_stats:
      self.booked_income = booked_stats.total_income()
      self.booked_expenses = booked_stats.total_expenses()
      self.booked_profit = booked_stats.net()
    else:
      self.booked_income = None
      self.booked_expenses = None
      self.booked_profit = None


def get_month_totals(
    from_date, today, to_date, owner_id, building_id, historic_month_income=[
        31746, 24353, 51925, 67190, 91915, 101038, 105873, 102237, 100528,
        23346, 31688, 62881]):
  if len(historic_month_income) != 12:
    raise Exception(
        'Should be one for each month.', len(historic_month_income))
  to_return = []
  stats_getter = StatsGetter()
  by_month = stats_getter.get_stats(
      from_date, to_date, MONTH, owner_id=owner_id, building_id=building_id)
  for stats in by_month:
    if stats.from_date.month < today.month:
      to_return.append(MonthTotals(stats.from_date, stats, None))
    elif stats.from_date.month > today.month:
      to_return.append(MonthTotals(stats.from_date, None, stats))
    else:
      past_total = stats_getter.get_stats(
          today.replace(day=1), today, TOTAL, owner_id=owner_id,
          building_id=building_id)
      booked_total = stats_getter.get_stats(
          today, add_months(today.replace(day=1), 1), TOTAL, owner_id=owner_id,
          building_id=building_id)
      to_return.append(MonthTotals(
          stats.from_date, past_total, booked_total))

  first_of_this_month = today.replace(day=1)
  last_3_months_total = stats_getter.get_stats(
      add_months(first_of_this_month, -3), first_of_this_month, TOTAL,
      owner_id=owner_id, building_id=building_id).total_income()

  # -1 because this function 0 indexes months, and today.month is 1 indexed.
  next_3 = _next_3_months_projected(
      last_3_months_total, today.month - 1, historic_month_income)
  for index, month in enumerate(to_return[-3:]):
    month.projected_income = next_3[index]
  return to_return


def _next_3_months_projected(
    last_3_months_total, month, historic_month_income):
  """ Month here is 0 indexed for easy math, and maximum confusion.
  last_3_months_total should be the income from the previous 3 months not
  including `month` added together. This will return an estimate for income for
  the next 3 months, starting with `month`. It just gets the ratio of your last
  3 months with our historic last 3 months, and multiplies the historic next 3
  months by that ratio. So if you made exactly half of the historic series in
  the past 3 months, you'll be projected to make exactly half the historic
  series for the next 3 months."""
  historic_last_3_months_total = 0
  for i in range(3):
    # -1 because we want to start checking on the previous month.
    check_month = (month - 1 - i) % 12
    historic_last_3_months_total += historic_month_income[check_month]

  ratio = last_3_months_total / historic_last_3_months_total

  to_return = []
  for i in range(3):
    check_month = (month + i) % 12
    to_return.append(historic_month_income[check_month] * ratio)

  return to_return


def get_from_today_to(today):
  from_date = today.replace(day=1, month=1)
  first_of_this_month = today.replace(day=1)
  to_date = add_months(first_of_this_month, 3)
  return (from_date, today, to_date)


def get_buildings(owner_id):
  return Building.objects.filter(
      owner_id=owner_id, is_active=True).annotate(
          rentals=Count('rental')).filter(rentals__gt=0)
