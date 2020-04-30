""" Serve up pages to virtual assistants. This can know about all kinds of
stuff. """
from datetime import date, timedelta
from unittest.mock import Mock

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, Http404
from django.shortcuts import render, reverse, redirect

from bgcheck.models.background_check import (
    must_cancel_reservations, must_cancel_reservations_table,
    bgchecks_for_vas, bgcheck_reservations_table)
from errors.models import notify
from front.models import Front
from guest_messages.models.message_list import get_message_list_table
from guest_messages.models.sms import do_resend_id_verification_link
from id_verify.models import Submission
from id_verify.models.risk_score import (
    high_risk_reservations_table, high_risk_reservations_for_vas)
from id_verify.models.submission_list import get_submission_list_table
from id_verify.models.inquiry_risk_score_calculator import InquiryRiskScoreForm
from id_verify.tests.test_risk_score import high_risk_submission
from rentals.models import Rental
from rentals.tests import get_test_city, get_test_building, get_test_rental
from reservations.models.money import Reservation
from reservations.reservation_finder import ReservationFinder
from reservations.tests.tests import get_test_reservation
from stripe.models import unlinked_charges_table, unlinked_charges
from util.admin import admin_context
from util.channels import AIRBNB
from util.permission import can_groups
from util.random_string import random_string
from util.web_test_users import get_superuser
from util.timezone import time_of_day_from_date, now
from util import twilio
from util.urls import nnow_from_query
from va.models import (
    reservations_table, reservation_meta_table, handle_checkin_instructions,
    Announcement, risk_css)
from va.verify_id_ui import handle_id_verify_list_post_or_problem


@login_required
@can_groups('id_verify', 'virtual_host')
def inquiry_risk_score_calculator(request):
  """ Inquiry level reservations should have a whole rad automated workflow.
  But we're not totally sure what that looks like yet, and in the meantime we
  ran out of money to use Typeform I guess, so the team really just needs a web
  form they can use in the meantime. """
  score = None
  form = InquiryRiskScoreForm()
  if request.method == 'POST':
    form = InquiryRiskScoreForm(request.POST)
    if form.is_valid():
      score = form.score()
  context = va_context(
      9, title='Inquiry reservation risk score calculator', form=form,
      score=score)
  return render(request, 'inquiry_risk_score_calculator.html', context=context)


@login_required
@can_groups('id_verify', 'virtual_host')
def reservations(
    request, reservation_view='va_reservation',
    template='va_reservations.html'):
  query = request.GET.get('q', '').strip()
  not_found = False
  if query:
    reservations = ReservationFinder().find(query)
    if len(reservations) == 1:
      return redirect(
          reverse(reservation_view, kwargs={'pk': reservations[0].pk}))
    elif len(reservations) == 0:
      not_found = True
  else:
    reservations = ReservationFinder().within_x_days(7)
  table = reservations_table(reservations, reservation_view)
  context = va_context(
      8, title='Reservations', table=table, not_found=not_found, query=query)
  return render(request, template, context=context)


@login_required
@can_groups('id_verify', 'virtual_host')
def va_reservation(request, pk):
  reservation = Reservation.objects.filter(pk=pk).first()
  if not reservation:
    return Http404('This reservation does not exist')
  meta_table = reservation_meta_table(reservation, request.user.is_superuser)
  title = '{} at {}'.format(
      reservation.guest.get_name(), reservation.rental.nickname)
  risk_score_css = risk_css(reservation)
  risk_score = reservation.riskscore_or_none
  risk_score_factors_table = None
  if risk_score is not None:
    risk_score_factors_table = reservation.riskscore.score_factors_as_table()
  context = va_context(
      8, title=title, meta_table=meta_table,
      message_list_table=get_message_list_table(reservation),
      risk_score_css=risk_score_css,
      risk_score=risk_score,
      risk_score_factors_table=risk_score_factors_table,
      submission_list_table=get_submission_list_table(
          reservation, is_superuser=request.user.is_superuser))
  context.update(handle_checkin_instructions(
      reservation, request.POST, request.user.is_superuser))
  return render(request, 'va_reservation.html', context=context)


@login_required
@can_groups('id_verify', 'virtual_host')
def submissions(request):
  problem = None
  if request.method == 'POST':
    problem = handle_id_verify_list_post_or_problem(
        request.POST, request.user, Front())
  submissions = Submission.objects.checkable_submissions(escalated=False)
  context = va_context(0, submissions=submissions, problem=problem)
  return render(request, 'va_submissions.html', context=context)


@login_required
@can_groups('id_verify', 'virtual_host')
def escalate_submission(request, submission_id):
  submission = Submission.objects.get(pk=submission_id)
  submission.escalated = True
  submission.escalated_by = request.user.email
  submission.save()
  url = 'https://admin.stayd.com{}'.format(reverse(
      'escalated_submissions', kwargs={'submission_id': submission_id}))
  notify(
      settings.ALERT_ESCALATED_SUBMISSION,
      'Warning: an admin escalated a submission', url)
  message = 'Escalated {}\'s submission'.format(
      submission.reservation.guest.get_name())
  return JsonResponse({'message': message})


@login_required
@can_groups('id_verify', 'virtual_host')
def escalated_submissions(request, submission_id=None):
  if request.method == 'POST':
    if request.POST.get('deescalate', None):
      Submission.objects.filter(
          pk=request.POST['submission_id']).update(escalated=False)
  if submission_id:
    submissions = Submission.objects.filter(pk=submission_id)
  else:
    submissions = Submission.objects.checkable_submissions(escalated=True)

  context = va_context(
      3, submissions=submissions, is_specific_submission=bool(submission_id))
  return render(request, 'escalated_submissions.html', context=context)


@login_required
@can_groups('id_verify', 'virtual_host')
def must_cancel(request):
  """ A list of reservations that must be canceled with a full refund. """
  nnow = nnow_from_query(request.GET)

  table = must_cancel_reservations_table(must_cancel_reservations(nnow=nnow))
  context = va_context(4, nnow=nnow, table=table)
  return render(request, 'must_cancel_reservations.html', context)


@login_required
@can_groups('id_verify', 'virtual_host')
def bgcheck(request):
  """ A list of reservations where we need to run a background check. """
  nnow = nnow_from_query(request.GET)

  table = bgcheck_reservations_table(bgchecks_for_vas(nnow=nnow))
  context = va_context(5, nnow=nnow, table=table)
  return render(request, 'va_bgchecks.html', context)


@login_required
@can_groups('id_verify', 'virtual_host')
def high_risk_approval(request):
  """ A list of reservations with high risk scores that need to be approved
  before we proceed. """
  nnow = nnow_from_query(request.GET)

  if request.method == 'POST':
    reservation_id = request.POST['reservation_id']
    reservation = Reservation.objects.get(pk=reservation_id)
    reservation.riskscore.reservation_approved_by = request.user
    reservation.riskscore.reservation_approved_at = nnow
    reservation.riskscore.save()

  table = high_risk_reservations_table(
      high_risk_reservations_for_vas())
  context = va_context(6, nnow=nnow, table=table)
  return render(request, 'va_high_risk_approval.html', context)


@login_required
@can_groups('virtual_host')
def over_charges(request):
  nnow = nnow_from_query(request.GET)
  table = unlinked_charges_table(nnow=nnow)
  context = va_context(7, nnow=nnow, table=table)
  return render(request, 'over_charges.html', context)


@login_required
@can_groups('id_verify', 'virtual_host')
def cc_action_required(request):
  reservations = Reservation.objects.cc_action_required().select_related(
      'guest', 'guestyreservation')
  context = va_context(1, reservations=reservations)
  return render(request, 'cc_action_required.html', context=context)


@login_required
@can_groups('virtual_host')
def no_cc_info(request):
  reservations = Reservation.objects.no_cc_info().select_related(
      'guest', 'guestyreservation')
  context = va_context(2, reservations=reservations)
  return render(request, 'no_cc_info.html', context=context)


def va_context(list_index, title=None, nnow=None, **kwargs):
  nnow = nnow or now()
  valid_count = Submission.objects.checkable_submissions(
      escalated=False).count()
  escalated_count = Submission.objects.checkable_submissions(
      escalated=True).count()
  must_cancel_count = must_cancel_reservations().count()
  bgcheck_count = bgchecks_for_vas(nnow=nnow).count()
  high_risk_count = high_risk_reservations_for_vas().count()
  over_charges_count = len(list(unlinked_charges(nnow=nnow)))
  announcements = [
      announcement.text for announcement in Announcement.objects.filter(
          start__lte=nnow, end__gte=nnow)]
  return admin_context(
      title or 'IDs and Credit Cards',
      announcements=announcements,
      valid_selected=list_index == 0,
      cc_action_required_selected=list_index == 1,
      no_cc_info_selected=list_index == 2,
      escalated_selected=list_index == 3,
      must_cancel_selected=list_index == 4,
      bgcheck_selected=list_index == 5,
      high_risk_selected=list_index == 6,
      over_charges_selected=list_index == 7,
      reservations_selected=list_index == 8,
      inquiry_risk_score_selected=list_index == 9,
      valid_url=reverse('submissions'),
      cc_action_required_url=reverse('cc_action_required'),
      no_cc_info_url=reverse('no_cc_info'),
      escalated_url=reverse('escalated_submissions'),
      must_cancel_url=reverse('must_cancel'),
      bgcheck_url=reverse('bgcheck'),
      high_risk_url=reverse('high_risk_approval'),
      over_charges_url=reverse('over_charges'),
      tickets_url=reverse('tickets'),
      reservations_url=reverse('va_reservations'),
      inquiry_risk_score_url=reverse('inquiry_risk_score_calculator'),
      cc_action_required_count=(
          Reservation.objects.cc_action_required().count()),
      valid_count=valid_count,
      no_cc_info_count=Reservation.objects.no_cc_info().count(),
      escalated_count=escalated_count,
      must_cancel_count=must_cancel_count,
      bgcheck_count=bgcheck_count,
      high_risk_count=high_risk_count,
      over_charges_count=over_charges_count,
      **kwargs)


@login_required
@can_groups('id_verify', 'virtual_host')
def resend_id_verification(request, reservation_id):
  return JsonResponse(do_resend_id_verification_link(reservation_id))


def get_reservation_for_high_risk_web_test(request):
  reservation = _get_test_reservation()
  has_is_voip = Mock(spec=twilio)
  has_is_voip.is_voip.return_value = True
  high_risk_submission(has_is_voip, reservation=reservation)
  return _res_json_response(reservation)


def get_reservation_for_id_verify_test(request):
  return _res_json_response(_get_test_reservation())


def _res_json_response(res):
  return JsonResponse({
      'pk': res.pk,
      'channel_id': res.channel_id,
      'guest_first_name': res.guest.first_name,
      'guest_full_name': res.guest.full_name})


def _get_test_reservation():
  if settings.PROD:
    raise Exception('Dont run web tests on production.')

  # The super user is probably going to verify the Id or approve the
  # reservation so we better make sure she exists.
  get_superuser()

  channel_id = random_string()
  check_in = time_of_day_from_date(date.today() + timedelta(days=2), 16)
  check_out = time_of_day_from_date(date.today() + timedelta(days=3), 11)
  first_name = 'Michael'
  full_name = 'Michael Jaindl'
  nickname = 'Slate - #337'
  rental = Rental.objects.filter(nickname=nickname).first()
  if not rental:
    street = '18220 North 68th Street'
    apartment = '#337'
    city_name = 'Phoenix'
    state = 'AZ'
    zipcode = '85054'
    country = 'United States'
    full_address = '{} {}, {}, {} {}, {}'.format(
        street, apartment, city_name, state, zipcode, country)
    city = get_test_city(
        name=city_name, state=state, country=country)
    building = get_test_building(
        city=city, nickname='Slate', street=street,
        zipcode=zipcode, time_zone='America/Phoenix')
    rental = get_test_rental(
        building=building, nickname=nickname, street=street,
        full_address=full_address)
  return get_test_reservation(
      guesty_id=random_string(), id_verified=False, channel=AIRBNB,
      channel_id=channel_id, check_in=check_in, check_out=check_out,
      first_name=first_name, full_name=full_name, rental=rental)
