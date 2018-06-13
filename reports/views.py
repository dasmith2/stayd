from datetime import datetime, timedelta, date
import json

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.urls import reverse

from guest_messages.models import Message
from guesty.models import GuestyReservation, RawEvent
from reports.rent_revenue.rent_revenue import get_rent_revenues
from reports.reservation_history.reservation_finder import ReservationFinder
from reports.reservation_history.webhook_describer import WebhookDescriber
from reservations.models import Reservation
from util.fake_admin import admin_context


DATE_FORMAT = '%m-%d-%Y'


@login_required
def rent_revenue(request, from_date_str='', to_date_str=''):
  """ The datepicker does 05/21/2018, but slashes and urls, so the js turns it
  to dashes first. So these date strings are coming in like 05-21-2018.
  Turn it back to slashes before it goes back out in the context so the
  template can speak the language of the picker. """
  if not from_date_str and not to_date_str:
    return redirect(reverse('rent_revenue', kwargs={
        'from_date_str': date_to_str(date.today()),
        'to_date_str': date_to_str(date.today() + timedelta(days=30))}))

  context = admin_context(
      'Revenue and market rent',
      from_date_str=from_date_str.replace('-', '/'),
      to_date_str=to_date_str.replace('-', '/'))

  if from_date_str and to_date_str:
    from_date = date_from_str(from_date_str)
    # OK, big fudge here. I feel like, for programmers it makes sense to
    # have an exclusive to_date, meaning that if you want to query about
    # February you do 2/1/2018 through 3/1/2018. But I think in the user
    # interface you'd expect to query 2/1/2018 through 2/28/2018.
    # So I add a day here.
    to_date = date_from_str(to_date_str) + timedelta(days=1)
    context['rent_revenues'] = get_rent_revenues(from_date, to_date)

  return render(request, 'rent_revenue.html', context=context)


@login_required
def reservation_search(request):
  query = request.GET.get('q', '').strip()
  context = admin_context(
      'Reservation history', not_found=False, multiple_results=False,
      query=query)
  if query:
    found_reservations = ReservationFinder().find(query)
    if len(found_reservations) == 1:
      return redirect(found_reservations[0].url)
    elif found_reservations:
      context['multiple_results'] = True
      context['found_reservations'] = found_reservations
    else:
      context['not_found'] = True
  return render(request, 'reservation_search.html', context=context)


@login_required
def reservation_history(request, pk):
  reservation = Reservation.objects.get(pk=pk)
  guesty_reservation = GuestyReservation.objects.get(reservation=reservation)
  # You have to do guest_messages because the Django admin templates look
  # for messages.
  context = admin_context(
      'Reservation history',
      guesty_reservation=guesty_reservation,
      reservation=reservation,
      guest_messages=Message.objects.get_for_reservation(
          reservation).order_by('-when_should'),
      webhook_diffs=WebhookDescriber().get_diffs(reservation))
  return render(request, 'reservation.html', context=context)


def see_raw_event_json(request, pk):
  return HttpResponse('<pre>{}</pre>'.format(
      json.dumps(json.loads(RawEvent.objects.get(pk=pk).json), indent=2)))


def date_to_str(dte):
  return dte.strftime(DATE_FORMAT)


def date_from_str(date_str):
  return datetime.strptime(date_str, DATE_FORMAT).date()
