from datetime import date

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import render

from rentals.models import Building
from stats.models.getter import StatsGetter
from stats.models.stats import MONTH, TOTAL
from stats.permission import Checker
from util.timezone import add_months


DASHBOARD_LOGIN = '/dashboard/login/'


@login_required(login_url=DASHBOARD_LOGIN)
def dashboard(request):
  owner_id = request.GET.get('owner_id', request.user.pk)
  building_id = request.GET.get('building_id', request.user.pk)
  problems = Checker().get_permission_problems(
      request.user, building_id=building_id, owner_id=owner_id)
  if problems:
    return problems

  from_date = date.today().replace(day=1, month=1)
  today = date.today()
  first_of_this_month = today.replace(day=1)
  to_date = add_months(first_of_this_month, 3)

  stats_getter = StatsGetter()
  year_to_date = stats_getter.get_stats(
      from_date, today, TOTAL, owner_id=owner_id)
  next_3_months_about = stats_getter.get_stats(
      today, to_date, TOTAL, owner_id=owner_id)

  buildings = Building.objects.filter(
      owner_id=owner_id, is_active=True).annotate(rentals=Count('rental'))
  context = {
      'owner_id': owner_id,
      'from_date': from_date,
      'today': today,
      'to_date': to_date,
      'year_to_date': year_to_date,
      'next_3_months_about': next_3_months_about,
      'by_month': _by_month(from_date, today, to_date, owner_id),
      'buildings': buildings}
  return render(request, 'dashboard.html', context=context)


def _by_month(from_date, today, to_date, owner_id):
  to_return = []
  stats_getter = StatsGetter()
  by_month = stats_getter.get_stats(
      from_date, to_date, MONTH, owner_id=owner_id)
  last_3_months_total = 0
  for stats in by_month:
    if stats.from_date.month < today.month:
      month_diff = today.month - stats.from_date.month
      if 0 < month_diff and month_diff < 4:
        last_3_months_total += stats.total_income()
      to_return.append(RealizedBooked(stats.from_date, stats, None))
    elif stats.from_date.month > today.month:
      to_return.append(RealizedBooked(stats.from_date, None, stats))
    else:
      realized_total = stats_getter.get_stats(
          today.replace(day=1), today, TOTAL, owner_id=owner_id)
      booked_total = stats_getter.get_stats(
          today, add_months(today.replace(day=1), 1), TOTAL, owner_id=owner_id)
      to_return.append(RealizedBooked(
          stats.from_date, realized_total, booked_total))
  next_3 = next_3_months_projected(last_3_months_total, today.month)
  for index, month in enumerate(to_return[-3:]):
    month.projected_profit = next_3[index]
  return to_return


def next_3_months_projected(last_3_months_total, month):
  """ Month here is 0 indexed for easy math, and maximum confusion :)
  last_3_months_total should be the income from the previous 3 months not
  including `month` added together. This will return an estimate for income for
  the next 3 months, starting with `month`. It just gets the ratio of your last
  3 months with our historic last 3 months, and multiplies the historic next 3
  months by that ratio. So if you made exactly half of the historic series in
  the past 3 months, you'll be projected to make exactly half the historic
  series for the next 3 months."""
  historic_month_income = [
      31746, 24353, 51925, 67190, 91915, 101038, 105873, 102237, 100528, 23346,
      31688, 62881]

  historic_last_3_months_total = 0
  for i in range(1, 4):
    check_month = (month - i) % 12
    historic_last_3_months_total += historic_month_income[check_month]

  ratio = last_3_months_total / historic_last_3_months_total

  to_return = []
  for i in range(3):
    check_month = (month + i) % 12
    to_return.append(historic_month_income[check_month] * ratio)

  return to_return


class RealizedBooked(object):
  def __init__(self, from_date, realized_stats, booked_stats):
    self.from_date = from_date
    self.projected_profit = None
    if realized_stats:
      self.month = realized_stats.from_date
      self.realized_income = realized_stats.total_income()
      self.realized_expenses = realized_stats.total_expenses()
      self.realized_profit = realized_stats.net()
    else:
      self.realized_income = None
      self.realized_expenses = None
      self.realized_profit = None
    if booked_stats:
      self.month = booked_stats.from_date
      self.booked_income = booked_stats.total_income()
      self.booked_expenses = booked_stats.total_expenses()
      self.booked_profit = booked_stats.net()
    else:
      self.booked_income = None
      self.booked_expenses = None
      self.booked_profit = None
