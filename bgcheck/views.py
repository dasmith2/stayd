from datetime import timedelta, date

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, reverse
from djmoney.money import Money

from bgcheck.models.background_check import door_person_table, BackgroundCheck
from bgcheck.models.dashboard import (
    dashboard_table, dashboard_totals, dashboard_table_reservations, detail)
from guests.tests import get_test_guest
from rentals.models import Building
from rentals.tests import get_test_rental, get_test_building
from reservations.models import Reservation
from reservations.tests import get_test_reservation, get_test_payment
from util.admin import simple_date_range_admin_page, simple_table_page
from util.channels import we_assume_cc_risk, we_take_security_deposit
from util.permission import VIRTUAL_HOST_GROUP, is_superuser
from util.web_test_users import get_web_test_user, VIRTUAL_HOST_USERNAME
from util.timezone import now
from util.urls import nnow_from_query, dates_from_strs
from util.views import message


@login_required
@is_superuser
def bgcheck_dashboard(request, from_date_str='', to_date_str=''):
  """ This table is filled with sensitive information. Basically nobody should
  get to see it. """
  not_allowed = _bgcheck_dashboard_not_allowed_response(request)
  if not_allowed:
    return not_allowed
  from_date, to_date, error = dates_from_strs(from_date_str, to_date_str)
  table = None
  if not error:
    table = dashboard_table(dashboard_table_reservations(from_date, to_date))
  return simple_date_range_admin_page(
      request, from_date_str, to_date_str, date.today() - timedelta(days=30),
      date.today() + timedelta(days=30),
      'bgcheck_dashboard', 'Background check dashboard', table=table)


@login_required
@is_superuser
def bgcheck_totals(request, from_date_str='', to_date_str=''):
  """ This table is filled with sensitive information. Basically nobody should
  get to see it. """
  not_allowed = _bgcheck_dashboard_not_allowed_response(request)
  if not_allowed:
    return not_allowed
  from_date, to_date, error = dates_from_strs(from_date_str, to_date_str)
  table = None
  if not error:
    table = dashboard_totals(dashboard_table_reservations(from_date, to_date))
  return simple_date_range_admin_page(
      request, from_date_str, to_date_str, date.today() - timedelta(days=30),
      date.today() + timedelta(days=30),
      'bgcheck_totals', 'Background check totals', table=table)


@login_required
@is_superuser
def bgcheck_detail(request, reservation_pk):
  not_allowed = _bgcheck_dashboard_not_allowed_response(request)
  if not_allowed:
    return not_allowed

  reservation = Reservation.objects.get(pk=reservation_pk)
  view_name_or_url = reverse(
      'bgcheck_detail', kwargs={'reservation_pk': reservation_pk})

  return simple_table_page(
      request, view_name_or_url, 'BGCheck detail', table=detail(reservation))


def _bgcheck_dashboard_not_allowed_response(request):
  if request.user.username not in ['dave', 'tom']:
    return message(
        'Not allowed',
        'Only tom and dave are allowed to view the background check dashboard',
        403)


@login_required
def door_person(request):
  door_person = request.user.doorperson_or_none

  nnow = nnow_from_query(request.GET)

  context = {'table': None, 'problem': None, 'title': None}
  if door_person:
    context['table'] = door_person_table(door_person.reservations(nnow=nnow))
    context['title'] = door_person.building.nickname
  else:
    problem = 'You don\'t appear to be a door person.'
    context['problem'] = problem
    context['title'] = problem
  return render(request, 'door_person.html', context)


def get_bg_check_reservation_data(request, channel):
  """ This is for web tests. """
  if settings.PROD:
    raise Exception('Dont create test data on production')

  get_web_test_user(VIRTUAL_HOST_USERNAME, groups=[VIRTUAL_HOST_GROUP])

  building = Building.objects.filter(background_check_guests=True).first()
  street = 'Hamilton Ave.'
  apartment = '#456'
  if not building:
    building = get_test_building(
        background_check_guests=True, city='Buffalo', country='USA',
        state='NY', street=street)
  rental = building.rental_set.first()
  if not rental:
    rental = get_test_rental(
        building=building, full_address='', street=street, apartment=apartment)
  guest = get_test_guest(
      full_name='Dave Blave', first_name='Dave', last_name='Blave')
  for reservation in rental.reservation_set.all():
    if reservation.backgroundcheck_or_none:
      reservation.backgroundcheck.delete()
    if reservation.riskscore_or_none:
      reservation.riskscore.delete()
    reservation.delete()
  check_in = (now() + timedelta(days=1)).replace(
      hour=16, minute=0, second=0, microsecond=0)
  check_out = (now() + timedelta(days=2)).replace(
      hour=11, minute=0, second=0, microsecond=0)
  reservation = get_test_reservation(
      check_in=check_in, check_out=check_out, guest=guest, rental=rental,
      room_line_item=100, channel=channel)
  if we_assume_cc_risk(reservation.channel):
    get_test_payment(reservation=reservation, cc_last_4=1234, cc_brand='VISA')
    reservation.cc_last_4 = 1234
    reservation.cc_brand = 'VISA'
    reservation.save()
  if we_take_security_deposit(reservation.channel):
    reservation.maximum_authorization_hold = Money(300, 'USD')
    reservation.save()
  return JsonResponse({
      'channel_id': reservation.channel_id, 'guest_name': guest.full_name})


def mark_passed(request, bgcheck_id, true_or_false):
  bgcheck = BackgroundCheck.objects.get(pk=int(bgcheck_id))
  bgcheck.set_passed(true_or_false.lower() == 'true')
  # I str this so Javascript doesn't have to capitalize it in order to keep
  # display consistent.
  return JsonResponse({'result': str(bgcheck.passed)})


def verify_us_id_cc(request, channel_id):
  if settings.PROD:
    raise Exception('Dont run web tests on prod')
  reservation = Reservation.objects.filter(channel_id=channel_id).first()
  problem = None
  if reservation:
    submission = reservation.submission_set.first()
    if submission:
      id_url = bool(submission.id_photo_url())
      cc_url = bool(submission.cc_photo_url())
      id_back_url = bool(submission.id_back_url())
      if not (id_url and cc_url and id_back_url):
        problem = 'A photo is missing. id: {}, cc: {}, id back: {}'.format(
            id_url, cc_url, id_back_url)
      if not submission.all_good():
        problem = 'The submission isnt all_good'
    else:
      problem = 'The submission doesnt exist'
  else:
    problem = 'The reservation doesnt exist'
  if problem:
    problem += '. Channel ID: {}. Reservation ID {}'.format(
        channel_id, reservation.pk)
  return JsonResponse({'valid': not problem, 'problem': problem})
