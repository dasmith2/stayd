import re

from django.shortcuts import reverse
from django.db.models import Q
from djmoney.money import Money

from commands.models import background_command
from work.models.work_co import WorkCo
from work.models.payment import Payment, WorkPayment
from work.models.work import Worker
from work.models.work_line_item import get_work_line_item_lookup
from util.table import Table, Cell
from util.urls import date_to_url_str


@background_command
def send_payment_background(payment_id, paypal_api=None):
  payment = Payment.objects.get(pk=payment_id).get_child_class_instance()
  if payment.tried_to_send():
    if payment.success() or payment.pending():
      return  # They probably just re-submitted the form.
    return payment.retry_pay(paypal_api=paypal_api)
  return payment.pay(paypal_api=paypal_api)


def handle_pay_service_providers_post(payments, request_post, paypal_api=None):
  send_these = set()
  pay_id_finder = re.compile(r'pay_(\d+)')
  for key, value in request_post.items():
    found = pay_id_finder.match(key)
    if found:
      send_these.add(int(found.groups()[0]))
  for pay in payments:
    pay.sending = pay.require_payment() and pay.pk in send_these
    if pay.sending:
      send_payment_background(pay.pk, paypal_api=paypal_api)


# I get the sense we've reached some kind of limit here. If you add another
# thing, sometimes the number of queries goes UP. I wonder if postgres is only
# willing to return so many columns. This has got to be, like, a thousand
# columns at this point.
PAYMENT_SELECT_RELATED = [
    'paypal_payout',
    'manualpayment',
    'manualpayment__worker',
    'manualpayment__worker__independentworker',
    'manualpayment__worker__workcoworker',
    'manualpayment__worker__workcoworker__work_co',
    'manualpayment__work_co',
    'manualpayment__building',
    'manualpayment__building__city',
    'manualpayment__building__owner',
    'workpayment',
    'workpayment__work',
    'workpayment__work__maintenance',
    'workpayment__work__maintenance__rental',
    'workpayment__work__maintenance__rental__building',
    'workpayment__work__maintenance__rental__building__city',
    'workpayment__work__maintenance__rental__building__owner',
    'workpayment__work__repeatwork',
    'workpayment__work__repeatwork__repeat_config__properly_rental__rental',  # noqa: E501
    'workpayment__work__repeatwork__repeat_config__properly_rental__rental__building',  # noqa: E501
    'workpayment__work__repeatwork__repeat_config__properly_rental__rental__building__city',  # noqa: E501
    'workpayment__work__repeatwork__repeat_config__properly_rental__rental__building__owner',  # noqa: E501
    'workpayment__work__oneoff',
    'workpayment__work__oneoff__properly_rental__rental',
    'workpayment__work__oneoff__properly_rental__rental__building',
    'workpayment__work__oneoff__properly_rental__rental__building__city',
    'workpayment__work__oneoff__properly_rental__rental__building__owner',  # noqa: E501
    'workpayment__work__cleaning',
    'workpayment__work__cleaning__rental',
    'workpayment__work__cleaning__rental__properlyrental',
    'workpayment__work__cleaning__rental__building',
    'workpayment__work__cleaning__rental__building__city',
    'workpayment__work__cleaning__rental__building__owner',
    'workpayment__work__inspection',
    'workpayment__work__inspection__inspect_cleaning__rental',
    'workpayment__work__inspection__inspect_cleaning__rental__building',
    'workpayment__work__inspection__inspect_cleaning__rental__building__city',
    'workpayment__work__inspection__inspect_cleaning__rental__building__owner',  # noqa: E501
    'workpayment__work__accepted_by__independentworker',
    'workpayment__work__accepted_by__workcoworker']


def get_pay_service_provider_payments(
    from_date, to_date, worker_id=None, work_co_id=None, owner_id=None,
    building_id=None, amount_gte=None, amount_lt=None, duration_gte=None,
    duration_lt=None, status=None):
  # These select relateds are to make the pay service providers page run fast
  manual_payment_work_completed = Q(
      manualpayment__work_completed__date__gte=from_date,
      manualpayment__work_completed__date__lt=to_date)
  manual_payment_created_at = Q(
      manualpayment__work_completed__isnull=True,
      manualpayment__created_at__date__gte=from_date,
      manualpayment__created_at__date__lt=to_date)
  work_payment_work_completed = Q(
      workpayment__work__completed_at__date__gte=from_date,
      workpayment__work__completed_at__date__lt=to_date)
  when_filter = manual_payment_work_completed | manual_payment_created_at | (
      work_payment_work_completed)
  unfiltered_payments = Payment.objects.filter(
      when_filter).select_related(*PAYMENT_SELECT_RELATED)

  payments = []
  # If you add any filters, make sure to add them to the
  # work.tests.test_pay_service_providers.PaymentActionTests
  # .test_get_pay_service_provider_payments_when_filter test.
  for pay in unfiltered_payments:
    pay = pay.get_child_class_instance()
    if worker_id and (
        (not pay.get_worker()) or pay.get_worker().pk != worker_id):
      continue
    if work_co_id and (
        (not pay.is_work_co()) or pay.get_work_co().pk != work_co_id):
      continue
    if building_id and (
        (not pay.get_bill_to_building()) or (
            pay.get_bill_to_building().pk != building_id)):
      continue
    if owner_id and (
        (not pay.get_bill_to_building()) or (
            not pay.get_bill_to_building().owner) or (
                pay.get_bill_to_building().owner.pk != owner_id)):
      continue
    if amount_gte or amount_lt:
      if not pay.can_calculate_amount():
        continue
      total_amount = pay.get_total_amount()
      if amount_gte and total_amount.amount < amount_gte:
        continue
      if amount_lt and total_amount.amount >= amount_lt:
        continue
    if duration_gte or duration_lt:
      if not pay.can_calculate_duration():
        continue
      if duration_gte and pay.get_reported_hours() < duration_gte:
        continue
      if duration_lt and pay.get_reported_hours() >= duration_lt:
        continue
    if status and pay.status() != status:
      continue
    payments.append(pay)

  # reversed returns an iterator that works once.
  # get_pay_service_provider_table runs through the list twice.
  return list(reversed(sorted(payments, key=lambda x: x.get_work_completed())))


def get_pay_service_provider_table(
    payments, can_send_payments=False, can_edit_payments=False):
  works = []
  for pay in payments:
    if isinstance(pay, WorkPayment):
      pay.work = pay.work.get_child_class_instance()
      works.append(pay.work)
  work_line_item_lookup = get_work_line_item_lookup(works)

  headers = []
  if can_send_payments:
    headers.append('<input id="select_all" type="checkbox">')
  work_completed_header = Cell(
      'Work completed', classes=['sorted'], is_header=True)
  total_amount = Money('0', 'USD')
  if payments:
    for pay in payments:
      if pay.can_calculate_amount():
        total_amount += pay.get_total_amount(
            work_line_item_lookup=work_line_item_lookup)
  headers.extend([
      'Invoice#', 'Description', 'Work at rental', 'Bill to building', 'Owner',
      'Payment created',
      'Payment sent', 'Work started', work_completed_header,
      'Amount (total: {})'.format(total_amount), 'Amount description',
      'Name', 'Email', 'Payment status', 'Requires payment',
      'On hold reason', 'Notes', 'Receipt'])
  table = Table(headers)
  for pay in payments:
    rental = pay.get_rental()
    rental_nickname = (rental and rental.nickname) or ''
    work_url = pay.get_work_url()
    bill_to_building = pay.get_bill_to_building()
    building_nickname_html = (
        bill_to_building and bill_to_building.city_nickname()) or ''
    building_nickname_csv = building_nickname_html or 'Q&A'
    owner_name = (
        bill_to_building and bill_to_building.owner and (
            bill_to_building.owner.email)) or ''
    row = table.create_row()
    # Subject is a combo of description, where, and when. This table has where
    # and when, so in html it would be redundant and a waste of space to use
    # get_subject. But, get_subject is the subject line for the paypal payment,
    # The accountants download a csv of paypal payouts and try to match them up
    # with the csv from keys. Hence the csv version uses get_subject instead of
    # get_description.
    description_cell = Cell(
        html_content=pay.get_description(), csv_content=pay.get_subject())
    if can_edit_payments:
      description_cell.url = pay.admin_url()
    if can_send_payments:
      pay_me_cell = Cell()
      if pay.require_payment() and pay.can_calculate_amount():
        pay_me_cell_format = """
            <input class="individual_checkbox"
                   data-amount="{}" name="pay_{}"
                   type="checkbox">"""
        pay_me_cell = Cell(
            pay_me_cell_format.format(pay.get_total_amount(
                work_line_item_lookup=work_line_item_lookup).amount, pay.pk))
      row.add(pay_me_cell)
    invoice_cell = Cell(pay.invoice_number(), url=reverse(
        'invoice', kwargs={'pay_pk': pay.pk}))
    # Invoice#, Description, Rental, Building, Owner, Payment created, Payment
    # sent, Work started, Work completed
    building_cell = Cell(
        html_content=building_nickname_html, csv_content=building_nickname_csv)
    row.extend([
        invoice_cell, description_cell, Cell(rental_nickname, url=work_url),
        building_cell, Cell(owner_name), Cell(pay.created_at),
        Cell(pay.paid_at()), Cell(pay.get_work_started() or ''),
        Cell(pay.get_work_completed() or '')])
    if not pay.can_calculate_amount():
      row.add_class('alert')
    receipt_cell = Cell()
    if pay.get_readable_type() == 'WorkPayment':
      amount = '???'
      describe_amount = None
      if pay.can_calculate_amount():
        amount = pay.get_total_amount(
            work_line_item_lookup=work_line_item_lookup).amount
        describe_amount = pay.describe_amount(
            work_line_item_lookup=work_line_item_lookup)
      else:
        describe_amount = pay.explain_why_cant_calculate_amount()
      row.extend([  # Amount, Amount description
          Cell(amount), Cell(describe_amount)])
    elif pay.get_readable_type() == 'ManualPayment':
      row.extend([  # Amount, Amount description
          Cell(pay.get_total_amount(
              work_line_item_lookup=work_line_item_lookup).amount), Cell()])
      if pay.receipt_photo_url:
        receipt_cell = Cell(img_url=pay.receipt_photo_url)

    name_cell = Cell(pay.vendor_name())
    email_cell = '???'
    if pay.is_work_co():
      work_co = pay.get_work_co()
      email_cell = Cell(work_co.owner.email)
      if can_send_payments:
        work_co_admin_url = reverse(
            'admin:work_workco_change', args=(work_co.pk,))
        name_cell.url = work_co_admin_url
        email_cell.url = work_co_admin_url
    else:
      worker = pay.get_worker()
      if worker:
        email_cell = Cell(worker.email)
        if can_send_payments:
          worker_admin_url = reverse(
              'admin:work_independentworker_change', args=(worker.pk,))
          name_cell.url = worker_admin_url
          email_cell.url = worker_admin_url

    # Name, Email, Payment status, Requires payment, On hold reason, Notes
    row.extend([
        name_cell, email_cell, Cell(pay.status()),
        Cell(pay.require_payment()), Cell(pay.on_hold_reason), Cell(pay.notes),
        receipt_cell])
  return table


def get_pay_service_provider_totals_table(from_date, to_date):
  # I pass in from_date and to_date instead of payments because we need the
  # from_date and to_date to make urls to see the details.
  payments = get_pay_service_provider_payments(from_date, to_date)
  per_recipient = {}
  statuses = set()
  for pay in payments:
    recipient_key = None
    recipient_name = '???'
    recipient_email = '???'
    recipient_type = None
    recipient_pk = None
    if pay.is_work_co():
      work_co = pay.get_work_co()
      recipient_key = 'work_co{}'.format(work_co.pk)
      recipient_name = work_co.name
      recipient_email = work_co.owner.email
      recipient_type = WorkCo
      recipient_pk = work_co.pk
    else:
      worker = pay.get_worker()
      if worker:
        recipient_key = 'worker{}'.format(worker.pk)
        recipient_name = worker.name
        recipient_email = worker.email
        recipient_type = Worker
        recipient_pk = worker.pk
    if recipient_key not in per_recipient:
      per_recipient[recipient_key] = {
          'per_status': {},  # payment per status, really
          'name': recipient_name,
          'email': recipient_email,
          'pk': recipient_pk,
          'jobs': 0,
          'hours': 0,
          'manual': 0,
          'recipient_type': recipient_type}
    data = per_recipient[recipient_key]
    if isinstance(pay, WorkPayment):
      pay.work = pay.work.get_child_class_instance()
      data['jobs'] += 1
      if pay.work.can_calculate_duration():
        data['hours'] += pay.work.get_actual_duration().seconds / 3600.0
        data['hours'] = round(data['hours'], 2)
    else:
      data['manual'] += 1

    if pay.can_calculate_amount():
      statuses.add(pay.status())
      if pay.status() in data['per_status']:
        data['per_status'][pay.status()] += pay.get_total_amount()
      else:
        data['per_status'][pay.status()] = pay.get_total_amount()

  statuses = list(statuses)
  headers = [
      'Name', 'Email', 'Jobs', 'Hours', 'Manual reimbursements'] + statuses
  table = Table(headers=headers)
  for data in sorted(per_recipient.values(), key=lambda x: x['name']):
    if data['recipient_type'] is WorkCo:
      query = '?work_co_id={}'.format(data['pk'])
    else:
      query = '?worker_id={}'.format(data['pk'])
    details_url = ''
    if data['pk']:
      details_url = reverse(
          'pay_service_providers', kwargs={
              'from_date_str': date_to_url_str(from_date),
              'to_date_str': date_to_url_str(to_date)}) + query
    cells = [
        Cell(data['name'], url=details_url), Cell(data['email']),
        Cell(data['jobs']), Cell(data['hours']), Cell(data['manual'])]
    for status in statuses:
      cells.append(Cell(data['per_status'].get(status, Money('0', 'USD'))))
    table.create_row(cells=cells)
  return table
