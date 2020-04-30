from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import render, reverse

from rentals.models import Building
from reports.cash_basis.revenue import (
    get_revenue_details_table, get_refund_details_table)
from util.admin import dated_admin_context
from util.permission import can_groups, ACCOUNTANT
from util.urls import dates_from_strs


@login_required
@can_groups(ACCOUNTANT)
def revenue_details(request, from_date_str, to_date_str, building_id):
  from_date, to_date, date_error = dates_from_strs(from_date_str, to_date_str)
  generate_csv_url = reverse(
      'revenue_details_csv', kwargs={
          'from_date_str': from_date_str, 'to_date_str': to_date_str,
          'building_id': building_id})
  building = Building.objects.get(pk=building_id)
  title = '{} Revenue'.format(building.nickname)
  context = dated_admin_context(
      title, from_date, to_date, date_error, request,
      generate_csv_url=generate_csv_url,
      breadcrumb_url=_breadcrumb_url(from_date_str, to_date_str))
  if not date_error:
    context['revenue_details_table'] = get_revenue_details_table(
        building, from_date, to_date)
  return render(request, 'cash_basis/revenue_details.html', context=context)


@login_required
@can_groups(ACCOUNTANT)
def revenue_details_csv(request, from_date_str, to_date_str, building_id):
  from_date, to_date, date_error = dates_from_strs(from_date_str, to_date_str)
  if date_error:
    return HttpResponseBadRequest('I was unable to parse the dates in the url')
  building = Building.objects.get(pk=building_id)
  return get_revenue_details_table(
      building, from_date, to_date).csv_response('cash_basis_revenue.csv')


@login_required
@can_groups(ACCOUNTANT)
def refund_details(request, from_date_str, to_date_str, building_id):
  from_date, to_date, date_error = dates_from_strs(from_date_str, to_date_str)

  generate_csv_url = reverse(
      'refund_details_csv', kwargs={
          'from_date_str': from_date_str, 'to_date_str': to_date_str,
          'building_id': building_id})
  building = Building.objects.get(pk=building_id)
  title = '{} Refund'.format(building.nickname)
  context = dated_admin_context(
      title, from_date, to_date, date_error, request,
      generate_csv_url=generate_csv_url,
      breadcrumb_url=_breadcrumb_url(from_date_str, to_date_str))
  if not date_error:
    context['refunds_table'] = get_refund_details_table(
        building, from_date, to_date)
  return render(request, 'cash_basis/refund_details.html', context=context)


def _breadcrumb_url(from_date_str, to_date_str):
  return reverse('cash_basis', kwargs={
      'from_date_str': from_date_str, 'to_date_str': to_date_str})


@login_required
@can_groups(ACCOUNTANT)
def refund_details_csv(request, from_date_str, to_date_str, building_id):
  from_date, to_date, date_error = dates_from_strs(from_date_str, to_date_str)
  if date_error:
    return HttpResponseBadRequest('I was unable to parse the dates in the url')
  building = Building.objects.get(pk=building_id)
  return get_refund_details_table(
      building, from_date, to_date).csv_response('cash_basis_refund.csv')
