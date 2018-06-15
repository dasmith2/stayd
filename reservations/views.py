from datetime import timedelta
import re

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils.timezone import now

from reservations.models import Reservation, CONFIRMED
from util.fake_admin import admin_context


@login_required
def cleaning_schedule(request):
  if request.method == 'POST':
    reservation_id_finder = re.compile(r'reservation_(\d+)')
    for key, value in request.POST.items():
      found = reservation_id_finder.match(key)
      if found:
        reservation_id = int(found.groups()[0])
        notes = request.POST['notes_{}'.format(reservation_id)]
        reservation = Reservation.objects.get(pk=reservation_id)
        reservation.cleaning_notes = notes
        reservation.save()
  context = admin_context(
      'Cleaning schedule',
      reservations=Reservation.objects.filter(
          status=CONFIRMED,
          check_out__gte=now(),
          check_out__lte=now() + timedelta(days=7)).order_by('check_out'))
  return render(request, 'cleaning.html', context=context)
