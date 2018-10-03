from datetime import date

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils.dateparse import parse_date

from dashboard.models import get_month_totals, get_from_today_to, get_buildings
from stats.models.getter import StatsGetter
from stats.models.stats import TOTAL
from stats.permission import Checker


DASHBOARD_LOGIN = '/dashboard/login/'


@login_required(login_url=DASHBOARD_LOGIN)
def dashboard(request):
  owner_id = request.GET.get('owner_id', request.user.pk)
  building_id = request.GET.get('building_id', 0)
  problems = Checker().get_permission_problems(
      request.user, owner_id=owner_id, building_id=building_id)
  if problems:
    return problems

  today = date.today()
  if 'date' in request.GET:  # Used in dashboard.tests
    today = parse_date(request.GET['date'])

  from_date, today, to_date = get_from_today_to(today)

  stats_getter = StatsGetter()
  year_to_date = stats_getter.get_stats(
      from_date, today, TOTAL, owner_id=owner_id, building_id=building_id)
  next_3_months_about = stats_getter.get_stats(
      today, to_date, TOTAL, owner_id=owner_id, building_id=building_id)

  # These are annotated with a `rentals` field which counts rentals.
  buildings = get_buildings(owner_id)

  context = {
      'owner_id': owner_id,
      'year_to_date': year_to_date,
      'next_3_months_about': next_3_months_about,
      'by_month': get_month_totals(
          from_date, today, to_date, owner_id, building_id),
      'buildings': buildings}
  return render(request, 'dashboard.html', context=context)
