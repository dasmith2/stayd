from collections import namedtuple
import csv
from datetime import timedelta, date
import json

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.urls import reverse

from guest_messages.models.models import SMS, Email
from guesty.models import GuestyReservation, RawEvent
from id_verify.models import Submission
from rentals.models import Building, Rental
from reports.rent_revenue.csv_writer import write_csv
from reports.rent_revenue.rent_revenue import get_rent_revenues
from reports.rent_revenue.reservation_list import ReservationList
from reports.reservation_history.webhook_describer import WebhookDescriber
from reservations.models import Reservation
from reservations.reservation_finder import ReservationFinder
from stats.models.stats import DAY
from stats.models.computer import compute_stats
from util.fake_admin import admin_context
from util.urls import date_to_url_str, dates_from_strs


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
      'Rent and revenue totals', from_date_str, to_date_str, request,
      owners=Rental.objects.get_owners())

  if from_date_str and to_date_str:
    from_date, to_date = dates_from_strs(from_date_str, to_date_str)
    context['rent_revenues'] = get_rent_revenues(
        from_date, to_date, _get_owner_id(request))

  return render(request, 'rent_revenue.html', context=context)


@login_required
def time_series(request, interval='', from_date_str='', to_date_str=''):
  if not from_date_str and not to_date_str:
    base_url = reverse('time_series', kwargs={
        'interval': DAY,
        'from_date_str': date_to_url_str(date.today() - timedelta(days=30)),
        'to_date_str': date_to_url_str(date.today() + timedelta(days=30))})
    return redirect(base_url + '?series=net')
  city = request.GET.get('city', None)
  title = 'Rent and revenue time series'
  if city:
    title += ': {}'.format(city)
  # Include all the data and let the Javascript decide what to actually
  # display.
  from_date, to_date = dates_from_strs(from_date_str, to_date_str)
  points = compute_stats(
      from_date, to_date, interval, city=city, owner_id=_get_owner_id(request))
  context = _dated_admin_context(
      title, from_date_str, to_date_str, request, points=points,
      owners=Rental.objects.get_owners())
  return render(request, 'time_series.html', context=context)


@login_required
def csv_options(request):
  rentals = Rental.objects.filter(is_active=True).order_by(
      'building__city', 'nickname')
  rental_pk_nicknames = [(rental.pk, rental.nickname) for rental in rentals]
  context = _dated_admin_context(
      'Rent and revenue CSV',
      date_to_url_str(date.today() - timedelta(days=30)),
      date_to_url_str(date.today() + timedelta(days=30)),
      request,
      city_names=Building.objects.city_names(),
      rental_pk_nicknames=rental_pk_nicknames)
  return render(request, 'csv_options.html', context=context)


@login_required
def csv_download(request):
  response = HttpResponse(content_type='text/csv')
  response['Content-Disposition'] = 'attachment; filename="rent_revenue.csv"'
  writer = csv.writer(response)
  from_date, to_date = dates_from_strs(
      request.GET['from_date_str'], request.GET['to_date_str'])
  interval = request.GET['interval']
  all_units_aggregate = 'all_units_aggregate' in request.GET
  cities = request.GET.get('cities', None) or None
  if cities:
    cities = cities.split(',')
  rental_ids = request.GET.get('rental_ids', None) or None
  if rental_ids:
    rental_ids = list([int(rental_id) for rental_id in rental_ids.split(',')])
  # The plural of series is series, but that doesn't do me much good for
  # variable names.
  seriesies = request.GET.get('series', None) or None
  if seriesies:
    seriesies = seriesies.split(',')
  write_csv(
      writer, from_date, to_date, interval, all_units_aggregate, cities,
      rental_ids, seriesies)
  return response


@login_required
def reservation_list(request, rental_id, from_date_str, to_date_str):
  from_date, to_date = dates_from_strs(from_date_str, to_date_str)
  list_getter = ReservationList(rental_id, from_date, to_date)
  context = _dated_admin_context(
      'Reservation list', from_date_str, to_date_str, request,
      rental=Rental.objects.get(pk=rental_id),
      nights_in_range=(to_date - from_date).days,
      res_deets_list=list_getter.get_res_deets_list(),
      back_to_rent_revenue=reverse('rent_revenue', kwargs={
          'from_date_str': from_date_str,
          'to_date_str': to_date_str}))
  return render(request, 'reservation_list.html', context=context)


class FoundReservation(
    namedtuple(
        'FoundReservation',
        'pk url channel_id check_in check_out full_name address')):
  pass


def found_reservation(reservation):
  return FoundReservation(
      pk=reservation.pk,
      url=reverse('reservation_history', kwargs={'pk': reservation.pk}),
      channel_id=reservation.channel_reservation_id,
      check_in=reservation.check_in,
      check_out=reservation.check_out,
      full_name=reservation.guest.full_name or reservation.guest.first_name,
      address=reservation.rental.full_address)


@login_required
def reservation_search(request):
  query = request.GET.get('q', '').strip()
  context = admin_context(
      'Reservation history', not_found=False, multiple_results=False,
      query=query)
  if query:
    reservations = ReservationFinder().find(query)
    found_reservations = [
        found_reservation(reservation) for reservation in reservations]
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
  smss = SMS.objects.get_for_reservation(reservation)
  emails = Email.objects.get_for_reservation(reservation)
  both = reversed(sorted(
      list(smss) + list(emails), key=lambda x: x.when_should))
  explain_why_no_confirmation = (
      Email.objects.explain_why_do_not_send_confirmation(reservation))
  # You have to do guest_messages because the Django admin templates look
  # for messages.
  context = admin_context(
      'Reservation history',
      in_guesty=bool(guesty_reservation),
      guesty_reservation=guesty_reservation,
      reservation=reservation,
      guest_messages=both,
      explain_why_do_not_send_confirmation=explain_why_no_confirmation,
      webhook_diffs=WebhookDescriber().get_diffs(reservation),
      submissions=Submission.objects.filter(
          reservation=reservation).order_by('created_at'))
  return render(request, 'reservation.html', context=context)


@login_required
def see_raw_event_json(request, pk):
  data = json.loads(RawEvent.objects.get(pk=pk).json)
  # Guesty is trying to be helpful by including logs of what happened
  # to the reservation, AND a copy of the reservation before INCLUDING LOGS.
  # Therefore, historic stuff comprises the overwhelming bulk of raw events.
  # But we have our own history of the reservation in saved raw events and
  # really just want to see what's in this particular raw event.
  if 'reservationBefore' in data:
    del data['reservationBefore']
  if 'reservation' in data:
    if 'log' in data['reservation']:
      del data['reservation']['log']
  return HttpResponse('<pre>{}</pre>'.format(json.dumps(data, indent=2)))


def _get_owner_id(request):
  return request.GET.get('owner_id', 0)


def _dated_admin_context(title, from_date_str, to_date_str, request, **kwargs):
  context = admin_context(
      title,
      from_date_str=from_date_str.replace('-', '/'),
      to_date_str=to_date_str.replace('-', '/'),
      **kwargs)
  owner_id = _get_owner_id(request)
  if owner_id:
    context['owner_id'] = int(owner_id)
  return context
