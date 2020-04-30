from django.db.models import Q
from django.shortcuts import reverse

from django.conf import settings
from errors.models import notify
from netsuite.models.netsuite_class import RentalClass, BuildingClass
from work.models.cleaning import Cleaning
from work.models.pay_service_providers import PAYMENT_SELECT_RELATED
from work.models.payment import Payment, WorkPayment
from util.table import Table
from util.urls import keys_url


def payments_for_netsuite_work_table(from_date, to_date):
  """ A csv downloadable table for the accountants that makes importing
  our work payment information to Netsuite a piece of cake. """
  work_payments_when = Q(
      workpayment__work__completed_at__date__gte=from_date,
      workpayment__work__completed_at__date__lt=to_date)
  manual_payments_when = Q(
      manualpayment__work_completed__date__gte=from_date,
      manualpayment__work_completed__date__lt=to_date)
  paid_out_auto = Q(paypal_payout__when_did__isnull=False)
  paid_out_manual = ~Q(manual_paypal_transaction_id='')
  payments = Payment.objects.filter(
      work_payments_when | manual_payments_when,
      paid_out_auto | paid_out_manual).select_related(*PAYMENT_SELECT_RELATED)
  payments = [pay.get_child_class_instance() for pay in payments]
  return sorted(payments, key=lambda x: x.get_work_completed())


CLEANING_COCONUT_NAME = 'Cleaning Services Expense'
CLEANING_COCONUT_CODE = 926
MAINTENANCE_COCONUT_NAME = 'Cleaning & Handyman Expense'
MAINTENANCE_COCONUT_CODE = 923


CSV_HEADERS = [
    'ExternalID', 'Reference No.', 'Vendor', 'Subsidiary', 'Location',
    'Account', 'Date', 'Posting Period', 'Due Date', 'Memo', 'Item',
    'Quantity', 'Description', 'Rate', 'Category', 'Account',
    'Account Internal ID', 'Amount', 'Terms', 'Class']


def netsuite_work_table(payments):
  table = Table(CSV_HEADERS)
  for payment in payments:
    table.create_row(_get_row(
        payment, payment.get_main_amount(), payment.get_subject()))
    for wli in payment.get_line_items():
      table.create_row(_get_row(payment, wli.amount, wli.description))
    if payment.sales_tax:
      table.create_row(_get_row(payment, payment.sales_tax, 'Sales tax'))
  return table


def _get_row(payment, amount, description):
  on_date = payment.get_work_completed().date()
  coconut_name = None
  coconut_code = None
  if isinstance(payment, WorkPayment):
    if isinstance(payment.work.get_child_class_instance(), Cleaning):
      coconut_name = CLEANING_COCONUT_NAME
      coconut_code = CLEANING_COCONUT_CODE
    else:
      coconut_name = MAINTENANCE_COCONUT_NAME
      coconut_code = MAINTENANCE_COCONUT_CODE
  location = None
  netsuite_class_code = None
  rental = payment.get_rental()
  if rental:
    location = rental.nickname
    if rental.netsuite_class_or_none:
      netsuite_class_code = rental.netsuite_class.code
    else:
      subject = 'What is the Netsuite Class for {}?'.format(rental.nickname)
      message = keys_url(reverse('netsuite_classes') + '#{}'.format(
          RentalClass(rental=rental).unique_id()))
      notify(settings.ALERT_NETSUITE_CONFIGURATION_REQUIRED, subject, message)
  else:
    building = payment.get_bill_to_building()
    if building:
      location = building.nickname
      if building.netsuite_class_or_none:
        netsuite_class_code = building.netsuite_class.code
      else:
        subject = 'What is the Netsuite Class for {}?'.format(
            building.nickname)
        message = keys_url(reverse('netsuite_classes') + '#{}'.format(
            BuildingClass(building=building).unique_id()))
        notify(
            settings.ALERT_NETSUITE_CONFIGURATION_REQUIRED, subject, message)
  return [
      payment.invoice_number(),  # ExternalID
      payment.invoice_number(),  # Reference No.
      payment.vendor_name(),  # Vendor
      None,  # Subsidiary
      location,  # Location
      None,  # Account
      on_date,  # Date
      None,  # Posting Period
      on_date,  # Due Date
      description,  # Memo
      None,  # Item
      None,  # Quantity
      None,  # Description
      None,  # Rate
      None,  # Category
      coconut_name,  # Account
      coconut_code,  # Account Internal ID
      amount,  # Amount
      None,  # Terms
      netsuite_class_code]  # Class
