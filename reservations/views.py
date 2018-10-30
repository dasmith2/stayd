from datetime import timedelta, date, datetime

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils.timezone import now, make_aware

from reservations.models import Reservation, CONFIRMED
from util.admin import admin_context


@login_required
def cleaning_schedule(request):
  exclude_ids = settings.EXCLUDE_CLEANING_SCHEDULE_IDS
  today = date.today()
  last_midnight = make_aware(datetime(today.year, today.month, today.day))
  context = admin_context(
      'Cleaning schedule',
      reservations=Reservation.objects.filter(
          status=CONFIRMED,
          check_out__gte=last_midnight,  # now() disappears too soon.
          check_out__lte=now() + timedelta(days=7)).exclude(
              rental__pk__in=exclude_ids).order_by('check_out'))
  return render(request, 'cleaning.html', context=context)
