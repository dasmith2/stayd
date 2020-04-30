from collections import namedtuple
import csv
from datetime import timedelta, date

from django.contrib.auth.decorators import login_required
from django.http import (
    HttpResponse, HttpResponseNotFound, HttpResponseBadRequest)
from django.shortcuts import render, redirect, reverse

from guest_messages.models.email import Email
from guest_messages.models.message_list import get_message_list_table
from guesty.models import GuestyReservation, RawEvent
from id_verify.models.submission_list import get_submission_list_table
from work.models.cleaning import Cleaning
from rentals.models import Rental, Building
from reports.rent_revenue.csv_writer import write_csv, SEPARATE
from reports.rent_revenue.rent_revenue import get_rent_revenues_table
from reports.rent_revenue.reservation_list import (
    get_all_res_deets, get_all_res_deets_for_csv)
from reports.reservation_history.webhook_describer import WebhookDescriber
from reports.occupancy import (
    get_occupancy, OVERBOOKED_COLOR, UNDERBOOKED_COLOR, WELLBOOKED_COLOR)
from reservations.models import Reservation
from stats.models.stats import DAY, WEEK, MONTH
from stats.models.computer import reservation_res_stats
from stats.models.getter import StatsGetter
from util.admin import admin_context, dated_admin_context
from util.csv import csv_writer_and_response
from util.permission import is_superuser, can_groups, ACCOUNTANT
from util.templatetags.util_extras import can_see_guests
from util.timezone import closest_previous_sunday, str_to_tz_dt
from util.urls import date_to_url_str, dates_from_strs


@login_required
@is_superuser
def occupancy_lookahead(request):
  nnow = request.GET.get('nnow', None)
  if nnow:
    nnow = str_to_tz_dt(nnow)
  context = admin_context(
      'Occupancy lookahead', occupancy=get_occupancy(nnow),
      overbooked_color=OVERBOOKED_COLOR, underbooked_color=UNDERBOOKED_COLOR,
      wellbooked_color=WELLBOOKED_COLOR)
  return render(request, 'occupancy_lookahead.html', context=context)


@login_required
@can_groups(ACCOUNTANT)
def rent_revenue(request, from_date_str='', to_date_str=''):
  if not from_date_str and not to_date_str:
    return redirect(reverse('rent_revenue', kwargs={
        'from_date_str': date_to_url_str(date.today()),
        'to_date_str': date_to_url_str(date.today() + timedelta(days=30))}))

  from_date, to_date, error = dates_from_strs(from_date_str, to_date_str)
  context = _owner_dated_admin_context(
      'Rent and revenue totals', from_date, to_date, error, request,
      owners=Rental.objects.get_owners())

  if not error:
    owner_id = _get_owner_id(request)
    context['rent_revenues_table'] = get_rent_revenues_table(
        from_date, to_date, owner_id)
    context['generate_csv_url'] = reverse('rent_revenue_totals_csv', kwargs={
        'from_date_str': from_date_str, 'to_date_str': to_date_str,
        'owner_id': owner_id})

  return render(request, 'rent_revenue.html', context=context)


@login_required
@can_groups(ACCOUNTANT)
def rent_revenue_totals_csv(request, from_date_str, to_date_str, owner_id):
  from_date, to_date, date_error = dates_from_strs(from_date_str, to_date_str)
  if date_error:
    return HttpResponseBadRequest('I was unable to parse the dates in the url')
  return get_rent_revenues_table(
      from_date, to_date, int(owner_id)).csv_response('rent_revenue.csv')


@login_required
@is_superuser
def time_series(request, interval='', from_date_str='', to_date_str=''):
  if not from_date_str and not to_date_str:
    base_url = reverse('time_series', kwargs={
        'interval': DAY,
        'from_date_str': date_to_url_str(date.today() - timedelta(days=30)),
        'to_date_str': date_to_url_str(date.today() + timedelta(days=30))})
    return redirect(base_url + '?series=net')
  title = 'Rent and revenue time series'
  # Include all the data and let the Javascript decide what to actually
  # display.
  from_date, to_date, error = dates_from_strs(from_date_str, to_date_str)
  context = _owner_dated_admin_context(
      title, from_date, to_date, error, request,
      owners=Rental.objects.get_owners())
  if not error:
    context['points'] = StatsGetter().get_stats(
        from_date, to_date, interval, owner_id=_get_owner_id(request))
  return render(request, 'time_series.html', context=context)


@login_required
@can_groups(ACCOUNTANT)
def csv_options(request):
  # Sometimes they want reports on inactive rentals.
  rentals = Rental.objects.filter(is_active=True).order_by(
      'building__city', 'building', 'nickname').select_related('building')
  RentalOption = namedtuple('RentalOption', 'pk nickname city')
  rental_options = []
  for rental in rentals:
    rental_options.append(RentalOption(
        pk=rental.pk, nickname=rental.nickname,
        city=rental.building.city.name))
  context = _owner_dated_admin_context(
      'Rent and revenue CSV',
      date.today() - timedelta(days=30),
      date.today() + timedelta(days=30),
      None,
      request,
      rental_options=rental_options)
  return render(request, 'csv_options.html', context=context)


@login_required
@can_groups(ACCOUNTANT)
def csv_download(request):
  response = HttpResponse(content_type='text/csv')
  response['Content-Disposition'] = 'attachment; filename="rent_revenue.csv"'
  writer = csv.writer(response)
  from_date, to_date, error = dates_from_strs(
      request.GET['from_date_str'], request.GET['to_date_str'])
  interval = request.GET['interval']
  if interval == MONTH:
    from_date = from_date.replace(day=1)
    to_date = to_date.replace(day=1)
  elif interval == WEEK:
    from_date = closest_previous_sunday(from_date)
    to_date = closest_previous_sunday(to_date)
  combine_or_separate = request.GET.get('combine_or_separate', SEPARATE)
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
      writer, from_date, to_date, interval, combine_or_separate, rental_ids,
      seriesies)
  return response


@login_required
@can_groups(ACCOUNTANT)
def reservation_list(
    request, from_date_str, to_date_str, rental_id=None, building_id=None):
  """ This is for when you click into the details of a rental in a date range
  from the totals page I believe. """
  if int(bool(rental_id)) + int(bool(building_id)) != 1:
    raise Exception('Specify exactly one of rental_id and building_id')

  url_kwargs = {'from_date_str': from_date_str, 'to_date_str': to_date_str}
  if rental_id:
    url_kwargs['rental_id'] = rental_id
  else:
    url_kwargs['building_id'] = building_id
  generate_csv_url = reverse('reservation_list_csv', kwargs=url_kwargs)

  from_date, to_date, error = dates_from_strs(from_date_str, to_date_str)
  what_are_we_talking_about = '???'
  if rental_id:
    what_are_we_talking_about = 'Rental: {}'.format(
        Rental.objects.get(pk=rental_id).nickname)
  elif building_id:
    what_are_we_talking_about = 'Building: {}'.format(
        Building.objects.get(pk=building_id).nickname)
  all_res_deets = get_all_res_deets(
      from_date, to_date, rental_id=rental_id, building_id=building_id)
  context = _owner_dated_admin_context(
      'Reservation list', from_date, to_date, error, request,
      what_are_we_talking_about=what_are_we_talking_about,
      nights_in_range=(to_date - from_date).days,
      res_deets_list=all_res_deets.res_deets_list,
      generate_csv_url=generate_csv_url,
      back_to_rent_revenue=reverse('rent_revenue', kwargs={
          'from_date_str': from_date_str,
          'to_date_str': to_date_str}))
  return render(request, 'reservation_list.html', context=context)


@login_required
@can_groups(ACCOUNTANT)
def reservation_list_csv(
    request, from_date_str, to_date_str, rental_id=None, building_id=None):
  from_date, to_date, error = dates_from_strs(from_date_str, to_date_str)
  writer, response = csv_writer_and_response('rent_revenue.csv')
  for row in get_all_res_deets_for_csv(
      from_date, to_date, rental_id=rental_id, building_id=building_id,
      include_guests=can_see_guests(request.user)):
    writer.writerow(row)
  return response


@login_required
@is_superuser
def reservation_search(request):
  from va.views import reservations
  return reservations(
      request, reservation_view='reservation_history',
      template='reservation_search.html')


@login_required
@is_superuser
def reservation_history(request, pk):
  reservation = Reservation.objects.filter(pk=pk).first()
  if not reservation:
    return HttpResponseNotFound('Reservation {} doesn\'t exist.'.format(pk))
  guesty_reservation = GuestyReservation.objects.filter(
      reservation=reservation).first()
  explain_why_no_confirmation = (
      Email.objects.explain_why_do_not_send_confirmation(reservation))
  cant_create_cleanings = (
      Cleaning.objects.explain_why_cant_create_cleanings_in_keys(reservation))
  # You have to do guest_messages because the Django admin templates look for
  # messages.
  context = admin_context(
      'Reservation history',
      in_guesty=bool(guesty_reservation),
      guesty_reservation=guesty_reservation,
      reservation=reservation,
      cleanings=reservation.cleaning_set.all(),
      message_list_table=get_message_list_table(reservation),
      explain_why_do_not_send_confirmation=explain_why_no_confirmation,
      explain_why_cant_create_cleanings_in_keys=cant_create_cleanings,
      webhook_diffs=WebhookDescriber().get_diffs(reservation),
      res_stats=reservation_res_stats(reservation),
      submission_list_table=get_submission_list_table(
          reservation, is_superuser=True))
  return render(request, 'reservation.html', context=context)


@login_required
@is_superuser
def see_raw_event_json(request, pk):
  return RawEvent.objects.get(pk=pk).as_html()


def _get_owner_id(request):
  return request.GET.get('owner_id', 0)


def _owner_dated_admin_context(
    title, from_date, to_date, date_error, request, **kwargs):
  context = dated_admin_context(
      title, from_date, to_date, date_error, request, **kwargs)
  owner_id = _get_owner_id(request)
  if owner_id:
    context['owner_id'] = int(owner_id)
  return context
