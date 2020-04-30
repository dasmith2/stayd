from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, reverse

from stripe.models import (
    Charge, UnlinkedChargeResolutionForm, handle_resolve_unlinked_charge_post)
from util.admin import dated_admin_context, simple_resolution_page
from util.permission import can_groups, ACCOUNTANT, is_superuser
from util.urls import date_to_url_str, dates_from_strs


@login_required
@can_groups(ACCOUNTANT)
def charge_to_reservation(request, from_date_str='', to_date_str=''):
  if not from_date_str and not to_date_str:
    return redirect(reverse('charge_to_reservation', kwargs={
        'from_date_str': date_to_url_str(date.today() - timedelta(days=30)),
        'to_date_str': date_to_url_str(date.today())}))
  from_date, to_date, error = dates_from_strs(from_date_str, to_date_str)
  charges = []
  if not error:
    charges = Charge.objects.filter(
        created__date__gte=from_date, created__date__lt=to_date)
  context = dated_admin_context(
      'Stripe charges to reservations', from_date, to_date, error, request,
      charges=charges)
  return render(request, 'charge_to_reservation.html', context=context)


@login_required
@is_superuser
def resolve_unlinked_charge(request, charge_id):
  charge = Charge.objects.get(pk=charge_id)
  back_to_list = redirect(reverse('over_charges'))
  if charge.unlinkedchargeresolution_or_none:
    return back_to_list
  title = 'Resolve {} {} {} {}'.format(
      charge.charge_id, charge.amount, charge.created.date(), charge.cc_last_4,
      charge.cc_brand)
  resolution_form = UnlinkedChargeResolutionForm()
  if request.method == 'POST':
    if handle_resolve_unlinked_charge_post(request.POST, charge):
      return back_to_list

  return simple_resolution_page(
      request, title, resolution_form,
      breadcrumb_url=reverse('over_charges'),
      breadcrumb_title='Over charges in Stripe',
      charge=charge)
