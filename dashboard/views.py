from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils.dateparse import parse_date
from util.timezone import now

from dashboard.models import get_month_totals, get_from_today_to, get_buildings
from stats.models.getter import StatsGetter
from stats.models.stats import TOTAL
from stats.permission import Checker


DASHBOARD_LOGIN = '/dashboard/login/'


@login_required(login_url=DASHBOARD_LOGIN)
def dashboard(request):
  owner_id = int(request.GET.get('owner_id', str(request.user.pk)))
  problems = Checker().get_permission_problems(request.user, owner_id=owner_id)
  if problems:
    return problems

  today = date.today()
  if 'date' in request.GET:  # Used in dashboard.tests
    today = parse_date(request.GET['date'])

  from_date, today, to_date = get_from_today_to(today)

  stats_getter = StatsGetter()
  year_to_date = stats_getter.get_stats(
      from_date, today, TOTAL, owner_id=owner_id)
  next_3_months_about = stats_getter.get_stats(
      today, to_date, TOTAL, owner_id=owner_id)

  building_id = None
  month_totals = get_month_totals(
      from_date, today, to_date, owner_id, building_id)

  mts = month_totals
  occupancy_peity = ','.join([
      str(mt.past_occupancy) for mt in mts if mt.past_occupancy is not None])
  adr_peity = ','.join([
      str(mt.past_adr) for mt in mts if mt.past_adr is not None])
  rev_par_peity = ','.join([
      str(mt.past_rev_par) for mt in mts if mt.past_rev_par is not None])
  avg_stay_peity = ','.join([
      str(mt.past_avg_stay) for mt in mts if mt.past_avg_stay is not None])

  five_hours_ago = (now() - timedelta(hours=5)).strftime('%B %d at %I:%M%p')

  context = {
      'year_to_date': year_to_date,
      'next_3_months_about': next_3_months_about,
      'occupancy_peity': occupancy_peity,
      'adr_peity': adr_peity,
      'rev_par_peity': rev_par_peity,
      'avg_stay_peity': avg_stay_peity,
      'by_month_enumerated': list(enumerate(month_totals)),
      'by_month_count': len(month_totals),
      'last_x_months': last_x_months(from_date, today),
      'last_logged_in': five_hours_ago}

  return render(request, 'dashboard.8.html', context=context)


def last_x_months(from_date, today):
  months = today.month - from_date.month
  if months == 0:
    return 'Just this month so far'
  return 'Last {} months'.format(months + 1)


@login_required(login_url=DASHBOARD_LOGIN)
def dashboard0(request):
  owner_id = int(request.GET.get('owner_id', str(request.user.pk)))
  building_id = int(request.GET.get('building_id', '0')) or None
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

  month_totals = get_month_totals(
      from_date, today, to_date, owner_id, building_id)

  context = {
      'owner_id': owner_id,
      'building_id': building_id,
      'year_to_date': year_to_date,
      'next_3_months_about': next_3_months_about,
      'by_month_enumerated': list(enumerate(month_totals)),
      'by_month_count': len(month_totals),
      'buildings': buildings}
  return render(request, 'dashboard.html', context=context)


def inbox(request):
  return render(request, 'app.inbox.html')
