from collections import namedtuple
from datetime import date

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from stats.models.getter import StatsGetter
from stats.models.stats import MONTH, TOTAL, Stats
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
  context = {
      'owner_id': owner_id,
      'from_date': from_date,
      'today': today,
      'to_date': to_date,
      'year_to_date': year_to_date,
      'next_3_months_about': next_3_months_about,
      'by_month': _by_month(from_date, today, to_date, owner_id)}
  return render(request, 'dashboard.html', context=context)


def _by_month(from_date, today, to_date, owner_id):
  to_return = []
  stats_getter = StatsGetter()
  by_month = stats_getter.get_stats(
      from_date, to_date, MONTH, owner_id=owner_id)
  for stats in by_month:
    if stats.from_date.month < today.month:
      to_return.append(RealizedBooked(stats, Stats()))
    elif stats.from_date.month > today.month or today.day == 1:
      to_return.append(RealizedBooked(Stats(), stats))
    else:
      realized_total = stats_getter.get_stats(
          today.replace(day=1), today, TOTAL, owner_id=owner_id)
      booked_total = stats_getter.get_stats(
          today, add_months(today.replace(day=1), 1), TOTAL, owner_id=owner_id)
      to_return.append(RealizedBooked(realized_total, booked_total))
  return to_return


class RealizedBooked(object):
  def __init__(self, realized_stats, booked_stats):
    self.month = realized_stats.from_date or booked_stats.from_date
    self.realized_expenses = realized_stats.total_expenses()
    self.realized_profit = realized_stats.net()
    self.booked_expenses = booked_stats.total_expenses()
    self.booked_profit = booked_stats.net()
