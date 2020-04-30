import csv
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, redirect, reverse
from djmoney.money import Money

from reservations.models import Reservation
from reservations.models.money import handle_resolve_payin_post, ResolutionForm
from util.admin import admin_context, simple_resolution_page
from util.permission import can_groups, ACCOUNTANT, is_superuser


@login_required
@is_superuser
def unresolved_likely_payin_not_ideal(request):
  generate_csv_url = reverse('unresolved_likely_payin_not_ideal_csv')
  return likely_payin_not_ideal_payin(
      request, resolved=False, generate_csv_url=generate_csv_url)


@login_required
@is_superuser
def unresolved_likely_payin_not_ideal_csv(request):
  return likely_payin_not_ideal_payin(request, resolved=False, csv=True)


@login_required
@can_groups(ACCOUNTANT)
def resolved_likely_payin_not_ideal(request):
  generate_csv_url = reverse('resolved_likely_payin_not_ideal_csv')
  return likely_payin_not_ideal_payin(
      request, resolved=True, generate_csv_url=generate_csv_url)


@login_required
@can_groups(ACCOUNTANT)
def resolved_likely_payin_not_ideal_csv(request):
  return likely_payin_not_ideal_payin(request, resolved=True, csv=True)


def likely_payin_not_ideal_payin(
    request, resolved=False, csv=False, generate_csv_url=''):
  reservations = Reservation.objects.likely_payin_not_ideal_payin()
  reservations = reservations.filter(resolution__isnull=not resolved)
  reservations = reservations.order_by('check_in')
  reservations = reservations.select_related(
      'rental', 'rental__building', 'guestyreservation', 'resolution')
  if csv:
    return likely_payin_not_ideal_payin_csv(reservations, resolved)
  title = '{}: Likely payin != ideal payin'.format(
      'Resolved' if resolved else 'Unresolved')
  context = admin_context(
      title,
      reservations=reservations,
      not_paid_enough_amount=Decimal('0'),
      not_paid_enough_count=0,
      paid_too_much_amount=Decimal('0'),
      paid_too_much_count=0,
      resolved=resolved,
      generate_csv_url=generate_csv_url)
  for reservation in reservations:
    actual_payin = reservation.get_actual_payin() or Money('0', 'USD')
    diff = actual_payin - reservation.ideal_payin
    if diff.amount < Decimal('0'):
      context['not_paid_enough_amount'] += diff
      context['not_paid_enough_count'] += 1
    else:
      context['paid_too_much_amount'] += diff
      context['paid_too_much_count'] += 1
  context['total_amount'] = (
      context['not_paid_enough_amount'] + context['paid_too_much_amount'])
  context['total_count'] = (
      context['not_paid_enough_count'] + context['paid_too_much_count'])
  return render(request, 'likely_payin_not_ideal_payin.html', context)


def likely_payin_not_ideal_payin_csv(reservations, resolved):
  """ Basically a copy of
  reservations/templates/likely_payin_not_ideal_payin.html """
  response = HttpResponse(content_type='text/csv')
  response['Content-Disposition'] = 'attachment; filename="payin_mismatch.csv"'
  writer = csv.writer(response)
  headers = [
      'Channel ID', 'Guest', 'Check in', 'Rental', 'Expected', 'Actual',
      'Balance due', 'Status', 'Guesty Notes']
  if resolved:
    headers.extend(['Resolution category', 'Resolution notes'])
  writer.writerow(headers)
  for reservation in reservations:
    row = [
        reservation.channel_id, reservation.guest.get_name(),
        reservation.check_in.date(), reservation.rental.nickname,
        reservation.ideal_payin, reservation.get_actual_payin(),
        reservation.get_balance_due(), reservation.status, reservation.issues]
    if resolved:
      row.extend([
          reservation.resolution.resolution_category.name,
          reservation.resolution.notes])
    writer.writerow(row)
  return response


@login_required
@is_superuser
def resolve_payin(request, pk):
  reservation = Reservation.objects.get(pk=pk)
  back_to_list = redirect(reverse('unresolved_likely_payin_not_ideal'))
  if reservation.resolution_or_none:
    return back_to_list
  title = 'Resolve {}\'s reservation checking in on {}'.format(
      reservation.guest.full_name, reservation.check_in.date())
  resolution_form = ResolutionForm()
  if request.method == 'POST':
    if handle_resolve_payin_post(request.POST, reservation):
      return back_to_list
  return simple_resolution_page(
      request, title, resolution_form, template='resolve_payin.html',
      breadcrumb_url=reverse('unresolved_likely_payin_not_ideal'),
      breadcrumb_title='Unresolved: Likely payin != ideal payin',
      reservation=reservation)
