from datetime import timedelta, date

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from errors.models import notify
from netsuite.models.netsuite_class import (
    all_possible_netsuite_classes, handle_netsuite_classes_post)
from netsuite.models.work_payments_table import (
    payments_for_netsuite_work_table, netsuite_work_table)
from netsuite.models.bill_table import bill_table, reservations_for_bill_table
from util.admin import simple_date_range_admin_page, admin_context
from util.permission import can_groups, ACCOUNTANT
from util.urls import dates_from_strs


@login_required
@can_groups(ACCOUNTANT)
def netsuite_classes(request):
  problems = []
  if request.method == 'POST':
    problems = handle_netsuite_classes_post(request.POST)
  context = admin_context(
      'Netsuite classes', netsuite_classes=all_possible_netsuite_classes(),
      problems=problems)
  return render(request, 'netsuite_classes.html', context=context)


@login_required
@can_groups(ACCOUNTANT)
def netsuite_csv_worker_payments(
    request, from_date_str='', to_date_str=''):
  # I'm not sure when I put this in, but today is 12/3/19
  subject = '{} is using Netsuite CSV: service provider payments'.format(
      request.user)
  notify('dave@hihoward.com', subject, 'That\'s a good thing.')
  from_date, to_date, error = dates_from_strs(from_date_str, to_date_str)
  table = None
  if not error:
    payments = payments_for_netsuite_work_table(from_date, to_date)
    table = netsuite_work_table(payments)
  return simple_date_range_admin_page(
      request, from_date_str, to_date_str, date.today() - timedelta(days=7),
      date.today() + timedelta(days=1),
      'netsuite_csv_worker_payments',
      'Netsuite CSV: Service provider payments', table=table)


@login_required
@can_groups(ACCOUNTANT)
def netsuite_csv_bill(
    request, from_date_str='', to_date_str=''):
  # I'm not sure when I put this in, but today is 12/3/19
  subject = '{} is using Netsuite CSV: revenue'.format(request.user)
  notify('dave@hihoward.com', subject, 'That\'s a good thing.')
  from_date, to_date, error = dates_from_strs(from_date_str, to_date_str)
  table = None
  if not error:
    table = bill_table(reservations_for_bill_table(from_date, to_date))
  return simple_date_range_admin_page(
      request, from_date_str, to_date_str, date.today() - timedelta(days=30),
      date.today() + timedelta(days=1),
      'netsuite_csv_bill',
      # The accountants are calling this revenue but it doesn't include payin
      # information. Honestly this table makes very little sense.
      'Netsuite CSV: Revenue', table=table)
