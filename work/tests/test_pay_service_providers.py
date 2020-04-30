from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import Mock

from django.conf import settings
from django.contrib.auth.models import User
from django.shortcuts import reverse
from djmoney.money import Money

from paypal.api import API as PaypalAPI
from paypal.api_examples import SUCCESSFULL_SEND
from paypal.models import SUCCESS, PENDING
from paypal.tests import get_test_payout, get_successful_payout
from rentals.models import Building
from rentals.tests import get_test_building, get_test_rental, get_test_owner
from work.models.pay_service_providers import (
    handle_pay_service_providers_post, get_pay_service_provider_payments,
    get_pay_service_provider_totals_table, get_pay_service_provider_table)
from work.models.payment import UNSENT
from work.models.sla import NEXT_CHECKOUT
from work.models.work import Work
from work.tests.test_cleaning import get_test_cleaning
from work.tests.test_maintenance import get_test_maintenance
from work.tests.test_one_off import get_test_one_off
from work.tests.test_work_co import get_test_work_co
from work.tests.test_work_co_worker import get_test_work_co_worker
from work.tests.test_payment import (
    get_test_work_payment, get_test_manual_payment)
from work.tests.test_rental import get_test_properly_rental
from work.tests.test_ticket import get_test_ticket, EXAMPLE_CHECKLIST_URL
from work.tests.test_work import get_test_independent_worker
from work.tests.test_work_line_item import get_test_work_line_item
from util.permission import ACCOUNTANT
from util.random_string import random_string
from util.table import Cell, Row
from util.tests import TestCase, get_test_user
from util.timezone import str_to_tz_dt, now


class PaymentExamplesTests(TestCase):
  """ This is a base class. Don't put any actual tests in here. """
  def setUp(self):
    super().setUp()
    set_my_payment_examples(self)


def set_my_payment_examples(self, offset_days=0):
  """ offset_days exists so I can make a whole bunch of these so I can get a
  better idea where the performance issues are on the pay service providers
  table. """
  if settings.PROD and not settings.TEST:
    raise Exception('Dont create testing data on PROD')

  def str_to_tz_dt_offset(dt_str):
    return str_to_tz_dt(dt_str) + timedelta(days=offset_days)

  suffix = str(offset_days) if offset_days else ''
  owner = get_test_owner(email='marc@marc.marc', username='marc')
  building = get_test_building(
      nickname='Marcs Palace' + suffix, owner=owner, city='London')

  self.indep_worker = get_test_independent_worker(
      hour_rate=Money('10.0', 'USD'), email='bob@indep.com' + suffix,
      name='Bob' + suffix, buildings=[building])
  independent_rental = get_test_rental(
      building=building, nickname='Indep Workers apt 1' + suffix)
  indep_work = get_test_cleaning(
      accepted_by=self.indep_worker,
      started_at=str_to_tz_dt_offset('2018-12-25 12:00'),
      completed_at=str_to_tz_dt_offset('2018-12-25 15:00'),
      rental=independent_rental)
  self.indep_work_payment = get_test_work_payment(
      work=indep_work, created_at=str_to_tz_dt_offset('2018-12-25 12:00'))

  self.manual_payment = get_test_manual_payment(
      subject='How are you from?' + suffix, message='But of course' + suffix,
      worker=self.indep_worker, building=building,
      receipt_photo_url='https://time.and/temperature.jpg',
      amount=Money('12.34', 'USD'),
      created_at=str_to_tz_dt_offset('2018-12-26 11:00'))

  self.work_co_rental = get_test_rental(
      building=building, nickname='Clean Co Workers apt 2' + suffix)
  jane = get_test_user(name='Jane', email='jane@cleaning.company')
  self.work_co = get_test_work_co(
      name='Janes Cleaning Company' + suffix, owner=jane,
      services_tax_rate=10)
  get_test_properly_rental(
      clean_co=self.work_co, rental=self.work_co_rental,
      cleaning_flat_rate=Money('53', 'USD'))
  work_co_worker = get_test_work_co_worker(
      email='jill@work_co.com' + suffix, work_co=self.work_co)
  self.clean_co_cleaning = get_test_cleaning(
      accepted_by=work_co_worker,
      started_at=str_to_tz_dt_offset('2018-12-24 12:00'),
      completed_at=str_to_tz_dt_offset('2018-12-24 15:00'),
      rental=self.work_co_rental)
  get_test_work_line_item(
      work=self.clean_co_cleaning, amount=Money('10', 'USD'),
      description='Fixed the couch', charge_sales_tax=True)
  self.work_co_payment = get_test_work_payment(
      work=self.clean_co_cleaning,
      created_at=str_to_tz_dt_offset('2018-12-24 12:00'))

  dave = get_test_owner(email='dave@dave.dave', username='dave')
  daves_building = get_test_building(
      nickname='Daves Swamp' + suffix, owner=dave, city='London',
      services_tax_rate=0)
  self.one_off = get_test_one_off(
      accepted_by=self.indep_worker,
      offered_start_time=str_to_tz_dt_offset('2018-12-24 12:00'),
      started_at=str_to_tz_dt_offset('2018-12-24 12:00'),
      completed_at=str_to_tz_dt_offset('2018-12-24 13:00'),
      rental=independent_rental, bill_to_building=daves_building,
      title='Razzle dazzle' + suffix)
  self.one_off_payment = get_test_work_payment(
      work=self.one_off, created_at=str_to_tz_dt_offset('2018-12-24 13:00'))


def pay_my_payment_examples(self):
  self.indep_work_payment.paypal_payout = get_successful_payout(
      amount=self.indep_work_payment.get_total_amount(),
      when_did=str_to_tz_dt('2018-12-26 12:00'))
  self.indep_work_payment.save()
  self.manual_payment.manual_paypal_transaction_id = random_string()
  self.manual_payment.manual_paypal_transaction_when = str_to_tz_dt(
      '2018-12-27 12:00')
  self.manual_payment.save()
  self.work_co_payment.paypal_payout = get_successful_payout(
      amount=self.work_co_payment.get_total_amount(),
      when_did=str_to_tz_dt('2018-12-27 12:00'))
  self.work_co_payment.save()
  self.one_off_payment.paypal_payout = get_successful_payout(
      amount=self.one_off_payment.get_total_amount(),
      when_did=str_to_tz_dt('2018-12-27 12:00'))
  self.one_off_payment.save()


def clean_up_my_payment_examples(self):
  # You only need this in web tests.
  for user in User.objects.filter(email='jane@cleaning.company'):
    for work_co in user.workco_set.all():
      for properly_rental in work_co.properlyrental_set.all():
        properly_rental.delete()
      for worker in work_co.workcoworker_set.all():
        _clean_up_worker(worker)
      work_co.delete()
    user.delete()
  for building in Building.objects.filter(
      owner__email__in=['dave@dave.dave', 'marc@marc.marc']):
    for one_off in building.oneoff_set.all():
      one_off.delete()
    for rental in building.rental_set.all():
      if rental.properlyrental_or_none:
        rental.properlyrental.delete()
      for cleaning in rental.cleaning_set.all():
        cleaning.delete()
      for reservation in rental.reservation_set.all():
        reservation.delete()
      rental.delete()
    for manual_payment in building.manualpayment_set.all():
      if manual_payment.paypal_payout:
        manual_payment.paypal_payout.delete()
      manual_payment.delete()
    for worker in building.independentworker_set.all():
      _clean_up_worker(worker)
    building.delete()


def _clean_up_worker(worker):
  for work in Work.objects.filter(accepted_by=worker):
    if work.workpayment_or_none:
      work.workpayment.paypal_payout.delete()
      work.workpayment.delete()
    work.get_child_class_instance().delete()
  worker.delete()


class MaintenanceTests(TestCase):
  def test_empty_maintenance(self):
    # As soon as I deployed tickets we got a maintenance job with a started and
    # completed yet no ticket, which broke the pay service providers page.
    maintenance = get_test_maintenance(
        offered_start_time=str_to_tz_dt('2018-12-25 12:00'),
        started_at=str_to_tz_dt('2018-12-25 12:00'),
        completed_at=str_to_tz_dt('2018-12-25 14:00'),
        accepted_by=get_test_independent_worker(),
        job_request_id='whatever')
    rental = get_test_rental()
    ticket = get_test_ticket(
        maintenance=maintenance, rental=rental, title='Do some stuff',
        sla=NEXT_CHECKOUT, existing_checklist_url=EXAMPLE_CHECKLIST_URL)
    maintenance.refresh_from_db()
    self.assertEqual(maintenance.rental, rental)
    payments = get_pay_service_provider_payments(
        date(2018, 12, 1), date(2019, 1, 1))
    self.assertEqual(1, len(payments))
    get_pay_service_provider_table(payments)

    # The ticket moves somewhere else!
    ticket.maintenance = None
    ticket.save()

    get_pay_service_provider_table(payments)


class PaymentActionTests(TestCase):
  def test_get_pay_service_provider_payments_when_filter(self):
    owner = get_test_owner()
    building = get_test_building(owner=owner)
    clean_co_worker = get_test_work_co_worker()
    properly_rental = get_test_properly_rental(
        building=building, clean_co=clean_co_worker.work_co,
        cleaning_flat_rate=Money('68.79', 'USD'))
    indep_work_payment = get_test_work_payment(
        started_at=str_to_tz_dt('2019-01-15 12:00'),
        completed_at=str_to_tz_dt('2019-01-15 14:00'),
        accepted_by=clean_co_worker, rental=properly_rental.rental)
    manual_payment_1 = get_test_manual_payment(
        work_completed=str_to_tz_dt('2019-01-15 14:30'),
        created_at=str_to_tz_dt('2019-01-17 14:00'))
    manual_payment_2 = get_test_manual_payment(
        created_at=str_to_tz_dt('2019-01-17 14:00'))

    self.assertEqual(
        [], get_pay_service_provider_payments(
            date(2019, 1, 14), date(2019, 1, 15)))
    self.assertEqual(
        [manual_payment_1, indep_work_payment],
        get_pay_service_provider_payments(
            date(2019, 1, 15), date(2019, 1, 16)))
    self.assertEqual(
        [manual_payment_2],
        get_pay_service_provider_payments(
            date(2019, 1, 17), date(2019, 1, 18)))

    # Lots of bugs in these filters! Run them all.
    self.assertEqual([indep_work_payment], get_pay_service_provider_payments(
        date(2019, 1, 15), date(2019, 1, 16),
        worker_id=indep_work_payment.get_worker().pk,
        work_co_id=indep_work_payment.get_work_co().pk,
        owner_id=owner.pk, building_id=building.pk, amount_gte=Decimal(0),
        amount_lt=Decimal(1000), duration_gte=Decimal(.01),
        duration_lt=Decimal(100), status=indep_work_payment.status()))

  def test_get_pay_service_provider_payments(self):
    bob = get_test_independent_worker(hour_rate=Money('10.0', 'USD'))
    sam = get_test_independent_worker()
    nnow = now()
    work = get_test_cleaning(
        accepted_by=bob, started_at=nnow - timedelta(hours=48),
        completed_at=nnow - timedelta(hours=45), services_tax_rate=0)
    get_test_work_payment(work=get_test_cleaning(
        accepted_by=sam, started_at=None,
        completed_at=nnow - timedelta(hours=45)))
    payment = get_test_work_payment(work=work)
    two_days_ago = now() - timedelta(days=2)
    a_day_from_now = now() + timedelta(days=1)

    self.assertTrue(payment in get_pay_service_provider_payments(
        two_days_ago, a_day_from_now))

    self.assertTrue(payment in get_pay_service_provider_payments(
        two_days_ago, a_day_from_now, worker_id=bob.pk,
        amount_gte=30, amount_lt=31, duration_gte=3, duration_lt=3.1))

    self.assertFalse(payment in get_pay_service_provider_payments(
        two_days_ago, a_day_from_now, worker_id=sam.pk))

    self.assertFalse(payment in get_pay_service_provider_payments(
        two_days_ago, a_day_from_now, amount_gte=31))

    self.assertFalse(payment in get_pay_service_provider_payments(
        two_days_ago, a_day_from_now, amount_lt=30))

    self.assertFalse(payment in get_pay_service_provider_payments(
        two_days_ago, a_day_from_now, duration_gte=3.1))

    self.assertFalse(payment in get_pay_service_provider_payments(
        two_days_ago, a_day_from_now, duration_lt=3))

  def test_retry_pay(self):
    paypal_api = Mock(spec=PaypalAPI)
    paypal_api.send_payout.return_value = SUCCESSFULL_SEND

    bob = get_test_independent_worker()
    work = get_test_cleaning(
        accepted_by=bob, started_at=str_to_tz_dt('2018-10-15 12:00'),
        completed_at=str_to_tz_dt('2018-10-15 13:00'))
    try:
      # This had better fail! Otherwise we'd send a duplicate payment.
      get_test_work_payment(
          work=work,
          paypal_payout=get_test_payout(batch_status=SUCCESS)).retry_pay()
      self.fail()
    except Exception:
      pass
    get_test_work_payment(
        work=work,
        paypal_payout=get_test_payout(batch_status='BAD_STUFF')).retry_pay(
            paypal_api=paypal_api)

  def test_handle_pay_service_providers_post(self):
    bob = get_test_independent_worker(name='Bob the slob')
    pay_for_work_1 = get_test_cleaning(
        accepted_by=bob, started_at=str_to_tz_dt('2018-10-15 12:00'),
        completed_at=str_to_tz_dt('2018-10-15 13:00'))
    pay_for_work_2 = get_test_cleaning(
        accepted_by=bob, started_at=str_to_tz_dt('2018-10-15 12:00'),
        completed_at=str_to_tz_dt('2018-10-15 13:00'))
    dont_pay_for_work = get_test_cleaning(
        accepted_by=bob, started_at=str_to_tz_dt('2018-10-16 12:00'),
        completed_at=str_to_tz_dt('2018-10-16 13:00'))

    pay_me = get_test_work_payment(work=pay_for_work_1)
    repay_me = get_test_work_payment(
        work=pay_for_work_2,
        paypal_payout=get_test_payout(batch_status='WENT_BAD_FOR_SOME_REASON'))
    dont_pay_me = get_test_work_payment(work=dont_pay_for_work)
    self.assertTrue(pay_me.require_payment())
    self.assertTrue(dont_pay_me.require_payment())
    request_post = {
        'pay_{}'.format(pay_me.pk): 'on', 'pay_{}'.format(repay_me.pk): 'on'}

    paypal_api = Mock(spec=PaypalAPI)
    paypal_api.send_payout.return_value = SUCCESSFULL_SEND

    handle_pay_service_providers_post(
        [pay_me, repay_me, dont_pay_me], request_post, paypal_api=paypal_api)
    pay_me.refresh_from_db()
    repay_me.refresh_from_db()
    dont_pay_me.refresh_from_db()

    self.assertEqual(2, len(paypal_api.send_payout.call_args_list))
    self.assertEqual(PENDING, pay_me.status())
    self.assertEqual(PENDING, repay_me.status())
    self.assertEqual(UNSENT, dont_pay_me.status())

    self.login(is_superuser=True)
    url_kwargs = {'from_date_str': '10-14-2018', 'to_date_str': '10-17-2018'}
    url = reverse('pay_service_providers', kwargs=url_kwargs)
    # Don't test for 'Bob the slob' in the html since he shows up in the
    # service providers filter no matter what.
    a_payment_url = reverse('admin:work_workpayment_change', args=(pay_me.pk,))
    self.assert_get_contains(url, a_payment_url)
    csv_url = reverse('pay_service_providers_csv', kwargs=url_kwargs)
    self.assert_get_contains(csv_url, 'Bob the slob')


class ReservationlessCleaningTests(TestCase):
  def test_get_pay_service_provider_table_no_reservation(self):
    cleaning = get_test_cleaning(
        reservation=None, rental=get_test_rental(),
        offered_start_time=str_to_tz_dt('2018-12-25 11:15'),
        accepted_by=get_test_independent_worker(),
        started_at=str_to_tz_dt('2018-12-25 11:15'),
        completed_at=str_to_tz_dt('2018-12-25 14:05'))
    get_pay_service_provider_table([get_test_work_payment(work=cleaning)])


class PaymentTableTests(PaymentExamplesTests):
  def test_cant_pay_full_time_employee(self):
    table = get_pay_service_provider_table(
        [self.one_off_payment], can_send_payments=True)
    self.assertTrue(table.rows[0].cells[0].html_content)
    self.assertEqual('UNSENT', table.rows[0].cells[14].html_content)

    self.indep_worker.full_time_employee = True
    self.indep_worker.save()
    self.one_off_payment.refresh_from_db()

    table = get_pay_service_provider_table(
        [self.one_off_payment], can_send_payments=True)
    self.assertFalse(table.rows[0].cells[0].html_content)
    self.assertEqual('NOT REQUIRED', table.rows[0].cells[14].html_content)

  def test_get_pay_service_provider_totals_table(self):
    table = get_pay_service_provider_totals_table(
        date(2018, 12, 1), date(2019, 1, 1))
    expected_headers = [
        'Name', 'Email', 'Jobs', 'Hours', 'Manual reimbursements', 'UNSENT']
    self.assertEqual(expected_headers, table.headers)
    url = (
        '/work/pay_service_providers/12-01-2018/01-01-2019/'
        '?worker_id={}').format(self.indep_worker.pk)
    # One cleaning for 3 hours at $10 an hour == $30. One manual payment for
    # $12.34. One one off for 1 hour == $10.
    table.rows[0].assertEqual(Row(cells=[
        Cell('Bob', url=url), Cell('bob@indep.com'), Cell(2), Cell(4), Cell(1),
        Cell(Money('52.34', 'USD'))]))
    work_co_url = (
        '/work/pay_service_providers/12-01-2018/01-01-2019/'
        '?work_co_id={}').format(self.work_co.pk)
    # 1 $53 flat rate cleaning + 10% sales tax = 58.30 plus one line item for
    # $10 + 10% sales tax = 11
    table.rows[1].assertEqual(Row(cells=[
        Cell('Janes Cleaning Company', url=work_co_url),
        Cell('jane@cleaning.company'), Cell(1),
        Cell(3), Cell(0), Cell(Money('69.30', 'USD'))]))

    self.login(group=ACCOUNTANT)
    url = reverse('pay_service_provider_totals', kwargs={
        'from_date_str': '12-01-2018', 'to_date_str': '01-01-2019'})
    self.assert_get_contains(url, 'bob@indep.com')

  def test_get_pay_service_provider_table_manual_payment_no_building(self):
    manual_payment = get_test_manual_payment()
    manual_payment.building = None
    manual_payment.save()
    get_pay_service_provider_table([manual_payment])

  def test_get_pay_service_provider_table(self):
    table = get_pay_service_provider_table([
        self.indep_work_payment, self.manual_payment, self.work_co_payment,
        self.one_off_payment], can_send_payments=False,
        can_edit_payments=False)
    # In order for checkboxes to appear, can_send_payments must be True.
    # $121.64 = 52.34 + 69.30
    expected_headers = [
        'Invoice#', 'Description', 'Work at rental', 'Bill to building',
        'Owner', 'Payment created', 'Payment sent', 'Work started',
        Cell('Work completed', classes=['sorted'], is_header=True),
        'Amount (total: $121.64)', 'Amount description', 'Name',
        'Email', 'Payment status', 'Requires payment', 'On hold reason',
        'Notes', 'Receipt']
    self.assertEqual(expected_headers, table.headers)

    description_cell = Cell(
        html_content='a cleaning',
        csv_content='a cleaning at Indep Workers apt 1 on 2018-12-25')
    invoice_url = reverse(
        'invoice', kwargs={'pay_pk': self.indep_work_payment.pk})
    table.rows[0].assertEqual(Row(cells=[
        Cell('cl{}'.format(self.indep_work_payment.pk), url=invoice_url),
        description_cell,
        Cell('Indep Workers apt 1', url=self.indep_work_payment.work.url()),
        Cell('London, ND: Marcs Palace'), Cell('marc@marc.marc'),
        Cell(str_to_tz_dt('2018-12-25 12:00')), Cell(),
        Cell(str_to_tz_dt('2018-12-25 12:00')),
        Cell(str_to_tz_dt('2018-12-25 15:00')), Cell(Decimal('30.00')),
        Cell('$10 * 03:00'), Cell('Bob'),
        Cell('bob@indep.com'), Cell('UNSENT'), Cell(True), Cell(), Cell(),
        Cell()]))

    descript_cell_2 = Cell(
        html_content='How are you from? But of course',
        csv_content='How are you from?')
    manual_url = reverse('invoice', kwargs={'pay_pk': self.manual_payment.pk})
    table.rows[1].assertEqual(Row(cells=[
        Cell('mp{}'.format(self.manual_payment.pk), url=manual_url),
        descript_cell_2, Cell(),
        Cell('London, ND: Marcs Palace'), Cell('marc@marc.marc'),
        Cell(str_to_tz_dt('2018-12-26 11:00')), Cell(),
        Cell(), Cell(str_to_tz_dt('2018-12-26 11:00')), Cell(Decimal('12.34')),
        Cell(), Cell('Bob'), Cell('bob@indep.com'), Cell('UNSENT'), Cell(True),
        Cell(), Cell(), Cell(img_url='https://time.and/temperature.jpg')]))

    cl_co_url = reverse(
        'invoice', kwargs={'pay_pk': self.work_co_payment.pk})
    description_cell_3 = Cell(
        html_content='a cleaning',
        csv_content='a cleaning at Clean Co Workers apt 2 on 2018-12-24')
    table.rows[2].assertEqual(Row(cells=[
        Cell('cl{}'.format(self.work_co_payment.pk), url=cl_co_url),
        description_cell_3,
        Cell('Clean Co Workers apt 2', url=self.work_co_payment.work.url()),
        Cell('London, ND: Marcs Palace'), Cell('marc@marc.marc'),
        Cell(str_to_tz_dt('2018-12-24 12:00')), Cell(),
        Cell(str_to_tz_dt('2018-12-24 12:00')),
        Cell(str_to_tz_dt('2018-12-24 15:00')), Cell(Decimal('69.30')),
        Cell('$53 flat rate + $10 line items + $6.30 tax'),
        Cell('Janes Cleaning Company'), Cell('jane@cleaning.company'),
        Cell('UNSENT'), Cell(True), Cell(), Cell(), Cell()]))

    oo_url = reverse(
        'invoice', kwargs={'pay_pk': self.one_off_payment.pk})
    description_cell_4 = Cell(
        html_content='Razzle dazzle',
        csv_content='Razzle dazzle at Indep Workers apt 1 on 2018-12-24')
    table.rows[3].assertEqual(Row(cells=[
        Cell('hm{}'.format(self.one_off_payment.pk), url=oo_url),
        description_cell_4,
        Cell('Indep Workers apt 1', url=self.one_off_payment.work.url()),
        Cell('London, ND: Daves Swamp'), Cell('dave@dave.dave'),
        Cell(str_to_tz_dt('2018-12-24 13:00')), Cell(),
        Cell(str_to_tz_dt('2018-12-24 12:00')),
        Cell(str_to_tz_dt('2018-12-24 13:00')), Cell(Decimal('10.00')),
        Cell('$10 * 01:00'), Cell('Bob'), Cell('bob@indep.com'),
        Cell('UNSENT'), Cell(True), Cell(), Cell(), Cell()]))

    self.login(group=ACCOUNTANT)
    url = reverse('pay_service_providers', kwargs={
        'from_date_str': '12-01-2018', 'to_date_str': '01-01-2019'})
    # Remember the page has tons of drop down list filters, so don't test
    # against, like, anybody or anything's name basically.
    self.assert_get_contains(url, '$10 * 01:00')
