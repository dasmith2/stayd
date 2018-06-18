from datetime import timedelta, date
import json

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.urls import reverse

from guest_messages.models import Message
from guesty.models import GuestyReservation, RawEvent
from rentals.models import Rental
from reports.rent_revenue.rent_revenue import get_rent_revenues
from reports.rent_revenue.reservation_list import ReservationList
from reports.reservation_history.reservation_finder import ReservationFinder
from reports.reservation_history.webhook_describer import WebhookDescriber
from reservations.models import Reservation
from util.fake_admin import admin_context
from util.url_date import date_from_url_str, date_to_url_str


@login_required
def rent_revenue(request, from_date_str='', to_date_str=''):
  """ The datepicker does 05/21/2018, but slashes and urls, so the js turns it
  to dashes first. So these date strings are coming in like 05-21-2018.
  Turn it back to slashes before it goes back out in the context so the
  template can speak the language of the picker. """
  if not from_date_str and not to_date_str:
    return redirect(reverse('rent_revenue', kwargs={
        'from_date_str': date_to_url_str(date.today()),
        'to_date_str': date_to_url_str(date.today() + timedelta(days=30))}))

  context = _dated_admin_context(
      'Rent and revenue', from_date_str, to_date_str)

  if from_date_str and to_date_str:
    from_date, to_date = _dates_from_strs(from_date_str, to_date_str)
    context['rent_revenues'] = get_rent_revenues(from_date, to_date)

  return render(request, 'rent_revenue.html', context=context)


@login_required
def reservation_list(request, rental_id, from_date_str, to_date_str):
  from_date, to_date = _dates_from_strs(from_date_str, to_date_str)
  list_getter = ReservationList(rental_id, from_date, to_date)
  context = _dated_admin_context(
      'Reservation list', from_date_str, to_date_str,
      rental=Rental.objects.get(pk=rental_id),
      nights_in_range=(to_date - from_date).days,
      res_deets_list=list_getter.get_res_deets_list(),
      back_to_rent_revenue=reverse('rent_revenue', kwargs={
          'from_date_str': from_date_str,
          'to_date_str': to_date_str}))
  return render(request, 'reservation_list.html', context=context)


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
  guesty_reservation = GuestyReservation.objects.filter(
      reservation=reservation).first()
  # You have to do guest_messages because the Django admin templates look
  # for messages.
  context = admin_context(
      'Reservation history',
      in_guesty=bool(guesty_reservation),
      guesty_reservation=guesty_reservation,
      reservation=reservation,
      guest_messages=Message.objects.get_for_reservation(
          reservation).order_by('-when_should'),
      webhook_diffs=WebhookDescriber().get_diffs(reservation))
  return render(request, 'reservation.html', context=context)


@login_required
def see_raw_event_json(request, pk):
  data = json.loads(RawEvent.objects.get(pk=pk).json)
  if 'reservation' in data:
    if 'log' in data['reservation']:
      # This can comprise the bulk of the JSON, and since we have a record
      # of webhooks going back 30 days, we don't need their log.
      del data['reservation']['log']
  return HttpResponse('<pre>{}</pre>'.format(json.dumps(data, indent=2)))


def _dates_from_strs(from_date_str, to_date_str):
  from_date = date_from_url_str(from_date_str)
  to_date = date_from_url_str(to_date_str)
  return (from_date, to_date)


def _dated_admin_context(title, from_date_str, to_date_str, **kwargs):
  return admin_context(
      title,
      from_date_str=from_date_str.replace('-', '/'),
      to_date_str=to_date_str.replace('-', '/'),
      **kwargs)
