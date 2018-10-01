from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

from stats.permission import Checker as PermissionChecker
from stats.models.stats import DAY, MONTH, TOTAL
from stats.models.getter import StatsGetter
from util.url_date import dates_from_strs


@login_required
def total_data(request, from_date_str, to_date_str):
  return time_series_data(request, TOTAL, from_date_str, to_date_str)


@login_required
def time_series_data(request, interval, from_date_str, to_date_str):
  from_date, to_date = dates_from_strs(from_date_str, to_date_str)
  rental_id = int(request.GET.get('rental_id', '0'))
  owner_id = int(request.GET.get('owner_id', '0'))

  permission_problems = PermissionChecker().get_permission_problems(
      request.user, rental_id=rental_id, owner_id=owner_id)
  if permission_problems:
    return permission_problems

  stats_result = StatsGetter().get_stats(
      from_date, to_date, interval, rental_id=rental_id, owner_id=owner_id)

  results = None
  if interval == TOTAL:
    results = stats_result.to_dict()
  elif interval in (DAY, MONTH):
    results = [stats.to_dict() for stats in stats_result]
  else:
    raise Exception(interval)

  return JsonResponse({'results': results})
