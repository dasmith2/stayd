from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock

from django.shortcuts import reverse
from djmoney.money import Money

from paypal.api import API as PaypalAPI
from paypal.api_examples import SUCCESSFULL_SEND
from paypal.tests import get_test_payout, get_successful_payout
from rentals.tests import get_test_building, get_test_city
from work.models.payment import Payment, ManualPayment, WorkPayment
from work.tests.test_cleaning import get_test_cleaning
from work.tests.test_one_off import get_test_one_off
from work.tests.test_rental import get_test_properly_rental
from work.tests.test_work import get_test_independent_worker
from work.tests.test_work_co import get_test_work_co
from work.tests.test_work_co_worker import get_test_work_co_worker
from work.tests.test_work_line_item import get_test_work_line_item
from util.permission import ACCOUNTANT
from util.tests import TestCase, get_test_user
from util.timezone import str_to_tz_dt, now


def get_test_work_payment(**kwargs):
  work = kwargs.get('work', None)
  if not work:
    from work.tests.test_cleaning import get_test_cleaning
    work = get_test_cleaning(**kwargs)
  work_payment = WorkPayment.objects.filter(work=work).first()
  # It only automatically makes the work payment if the work has a completed_at
  if not work_payment:
    work_payment = WorkPayment(work=work)
  work_payment.hours_override = kwargs.get('hours_override', None)
  return set_payment_stuff(work_payment, **kwargs)


def get_test_manual_payment(**kwargs):
  if 'rental' in kwargs:
    raise Exception('ManualPayments now only have buildings, not rentals.')
  building = kwargs.get('building', None)
  if not building:
    building = get_test_building(**kwargs)
  worker = kwargs.get('worker', None)
  work_co = kwargs.get('work_co', None)
  if not worker and not work_co:
    worker = get_test_independent_worker()
  work_completed = kwargs.get(
      'work_completed', kwargs.get('created_at', now()))
  manual_payment = ManualPayment(
      subject=kwargs.get('subject', 'subject here'),
      message=kwargs.get('message', 'message here'),
      worker=worker,
      work_co=work_co,
      building=building,
      receipt_photo_url=kwargs.get('receipt_photo_url', ''),
      amount=kwargs.get('amount', Money('10.0', 'USD')),
      work_completed=work_completed)
  return set_payment_stuff(manual_payment, **kwargs)


def set_payment_stuff(instance, **kwargs):
  instance.paypal_payout = kwargs.get('paypal_payout', None)
  instance.on_hold_reason = kwargs.get('on_hold_reason', '')
  instance.save()
  if 'created_at' in kwargs:
    Payment.objects.filter(pk=instance.pk).update(
        created_at=kwargs['created_at'])
    instance.refresh_from_db()
  return instance


class IsWorkCoTests(TestCase):
  def test_indep_rental_accepted_by_clean_co_worker(self):
    indep_properly_rental = get_test_properly_rental()
    self.assertTrue(get_test_work_payment(
        work=get_test_cleaning(
            rental=indep_properly_rental.rental,
            accepted_by=get_test_work_co_worker())).is_work_co())

  def test_clean_co_rental_accepted_by_independent_worker(self):
    work_co_properly_rental = get_test_properly_rental(
        clean_co=get_test_work_co())
    self.assertFalse(get_test_work_payment(
        work=get_test_cleaning(
            rental=work_co_properly_rental.rental,
            accepted_by=get_test_independent_worker())).is_work_co())

  def test_indep_rental_not_accepted(self):
    indep_properly_rental = get_test_properly_rental()
    self.assertFalse(get_test_work_payment(
        work=get_test_cleaning(
            rental=indep_properly_rental.rental)).is_work_co())

  def test_clean_co_rental_not_accepted(self):
    work_co_properly_rental = get_test_properly_rental(
        clean_co=get_test_work_co())
    self.assertTrue(get_test_work_payment(
        work=get_test_cleaning(
            rental=work_co_properly_rental.rental)).is_work_co())

  def test_manual_payment_work_co(self):
    self.assertTrue(get_test_manual_payment(
        work_co=get_test_work_co()).is_work_co())

  def test_manual_payment_work_co_worker(self):
    self.assertTrue(get_test_manual_payment(
        worker=get_test_work_co_worker()).is_work_co())

  def test_manual_payment_indep_worker(self):
    self.assertFalse(get_test_manual_payment(
        worker=get_test_independent_worker()).is_work_co())


class PaymentTests(TestCase):
  def test_cant_calculate_work_co_amount(self):
    sam = get_test_work_co_worker()
    properly_rental = get_test_properly_rental(
        clean_co=sam.work_co, cleaning_flat_rate=None)
    payment = get_test_work_payment(
        accepted_by=sam, rental=properly_rental.rental)
    self.assertTrue(payment.is_work_co())
    self.assertFalse(payment.can_calculate_amount())

  def test_invoice(self):
    nnow = now()
    bob = get_test_independent_worker(
        hour_rate=Money('10.0', 'USD'), name='Bob Slob')
    work = get_test_cleaning(
        accepted_by=bob, started_at=nnow - timedelta(hours=48),
        completed_at=nnow - timedelta(hours=45))
    work_payment = get_test_work_payment(work=work)
    manual_payment = get_test_manual_payment(worker=bob)
    self.login(group=ACCOUNTANT)
    self.assert_get_contains(
        reverse('invoice', kwargs={'pay_pk': work_payment.pk}), 'Bob Slob')
    self.assert_get_contains(
        reverse('invoice', kwargs={'pay_pk': manual_payment.pk}), 'Bob Slob')

  def test_describe_work_co_amount(self):
    worker = get_test_work_co_worker(services_tax_rate=10)
    work = get_test_cleaning(
        cleaning_flat_rate=Money('20', 'USD'), accepted_by=worker,
        started_at=str_to_tz_dt('2018-10-15 12:00'),
        completed_at=str_to_tz_dt('2018-10-15 13:00'))
    pay = WorkPayment.objects.get(work=work)
    self.assertEqual('$20 flat rate + $2 tax', pay.describe_amount())

  def test_describe_indep_amount(self):
    worker = get_test_independent_worker(
        hour_rate=Money('10.0', 'USD'), hour_min=2)
    work = get_test_cleaning(
        accepted_by=worker, started_at=str_to_tz_dt('2018-10-15 12:00'),
        completed_at=str_to_tz_dt('2018-10-15 13:00'))
    pay = WorkPayment.objects.get(work=work)
    self.assertEqual(
        '$10 * 02:00 (hour minimum)', pay.describe_amount())
    work.completed_at = str_to_tz_dt('2018-10-15 15:00')
    work.save()
    pay.refresh_from_db()
    self.assertEqual(
        '$10 * 03:00', pay.describe_amount())
    pay.hours_override = Decimal('1')
    pay.save()
    self.assertEqual(
        '$10 * 01:00 (hours override)', pay.describe_amount())

  def test_require_payment(self):
    paid_already = get_test_work_payment(
        paypal_payout=get_successful_payout())
    self.assertFalse(paid_already.require_payment())

    payout_but_not_paid = get_test_work_payment(
        paypal_payout=get_test_payout(batch_status=''))
    self.assertTrue(payout_but_not_paid.require_payment())

    unsuccessful_payout = get_test_work_payment(
        paypal_payout=get_test_payout(batch_status='Blargh!'))
    self.assertTrue(unsuccessful_payout.require_payment())

    no_payout = get_test_work_payment()
    self.assertTrue(no_payout.require_payment())

    on_hold_reason = get_test_work_payment(
        on_hold_reason='I just dont like this guy')
    self.assertFalse(on_hold_reason.require_payment())

    manual = get_test_manual_payment()
    self.assertTrue(manual.require_payment())

    full_time_employee_payment = get_test_work_payment()
    # Well, not full time yet...
    full_time_employee = get_test_independent_worker()
    work = full_time_employee_payment.work.get_child_class_instance()
    work.accepted_by = full_time_employee
    work.save()
    self.assertTrue(full_time_employee_payment.require_payment())
    full_time_employee.full_time_employee = True
    full_time_employee.save()
    self.assertFalse(full_time_employee_payment.require_payment())

    manual_2 = get_test_manual_payment()
    self.assertTrue(manual_2.require_payment())
    manual_2.manual_paypal_transaction_id = 'blarbityblar'
    manual_2.manual_paypal_transaction_when = str_to_tz_dt('2018-12-25 12:00')
    self.assertFalse(manual_2.require_payment())
    self.assertTrue(manual_2.success())
    self.assertEqual(str_to_tz_dt('2018-12-25 12:00'), manual_2.paid_at())

  def test_pay_payout_does_not_exist(self):
    paypal_api = Mock(spec=PaypalAPI)
    paypal_api.send_payout.return_value = SUCCESSFULL_SEND

    worker = get_test_independent_worker(email='worker@worker.com')
    payment = get_test_work_payment(
        paypal_payout=None, accepted_by=worker,
        started_at=str_to_tz_dt('2018-10-15 12:00'),
        completed_at=str_to_tz_dt('2018-10-15 13:00'))
    payment.pay(paypal_api=paypal_api)

    self.assertEqual('P8Z8TRV7P', payment.paypal_payout.payout_batch_id)
    self.assertEqual('worker@worker.com', payment.paypal_payout.pay_email)

  def test_pay_work_co(self):
    paypal_api = Mock(spec=PaypalAPI)
    paypal_api.send_payout.return_value = SUCCESSFULL_SEND

    owner = get_test_user(email='owner@owner.com')
    work_co = get_test_work_co(owner=owner)
    worker = get_test_work_co_worker(
        work_co=work_co, email='worker@worker.com')
    properly_rental = get_test_properly_rental(
        clean_co=work_co, cleaning_flat_rate=Money('68', 'USD'))
    payment = get_test_work_payment(
        paypal_payout=None, accepted_by=worker,
        started_at=str_to_tz_dt('2018-10-15 12:00'),
        completed_at=str_to_tz_dt('2018-10-15 13:00'),
        rental=properly_rental.rental)

    payment.pay(paypal_api=paypal_api)

    self.assertEqual('P8Z8TRV7P', payment.paypal_payout.payout_batch_id)
    self.assertEqual('owner@owner.com', payment.paypal_payout.pay_email)

  def test_pay_payout_does_exist(self):
    paypal_api = Mock(spec=PaypalAPI)
    paypal_api.send_payout.return_value = SUCCESSFULL_SEND

    payment = get_test_work_payment(
        paypal_payout=get_test_payout(batch_status=''))
    payment.pay(paypal_api=paypal_api)

    self.assertEqual('P8Z8TRV7P', payment.paypal_payout.payout_batch_id)

  def test_get_payment_email(self):
    work_co_owner = get_test_user(email='work@co.com')
    work_co = get_test_work_co(owner=work_co_owner)
    work_co_worker = get_test_work_co_worker(
        work_co=work_co, email='work_co@worker.com')
    independent_worker = get_test_independent_worker(
        email='independent@worker.com')
    self.assertEqual(
        'work@co.com',
        get_test_manual_payment(work_co=work_co).get_payment_email())
    work_co_work = get_test_one_off(
        offered_start_time=str_to_tz_dt('2018-12-25 12:00'),
        started_at=str_to_tz_dt('2018-12-25 12:00'),
        completed_at=str_to_tz_dt('2018-12-25 13:00'),
        accepted_by=work_co_worker)
    self.assertEqual(
        'work@co.com',
        get_test_work_payment(work=work_co_work).get_payment_email())
    self.assertEqual(
        'independent@worker.com',
        get_test_manual_payment(worker=independent_worker).get_payment_email())
    independent_work = get_test_one_off(
        offered_start_time=str_to_tz_dt('2018-12-25 12:00'),
        started_at=str_to_tz_dt('2018-12-25 12:00'),
        completed_at=str_to_tz_dt('2018-12-25 13:00'),
        accepted_by=independent_worker)
    self.assertEqual(
        'independent@worker.com',
        get_test_work_payment(work=independent_work).get_payment_email())


class SalesTaxTests(TestCase):
  def setUp(self):
    super().setUp()
    self.clean_co = get_test_work_co(services_tax_rate=7)
    self.city = get_test_city()
    properly_rental = get_test_properly_rental(
        clean_co=self.clean_co, cleaning_flat_rate=Money('1000', 'USD'),
        city=self.city)
    self.clean = get_test_cleaning(
        rental=properly_rental.rental,
        check_in=str_to_tz_dt('2018-12-25 16:00'),
        check_out=str_to_tz_dt('2018-12-26 11:00'),
        started_at=str_to_tz_dt('2018-12-26 11:15'),
        completed_at=str_to_tz_dt('2018-12-26 14:00'))

  def test_workpayment(self):
    self.assertEqual(Money('70', 'USD'), self.clean.workpayment.sales_tax)

  def test_wli_update_updates(self):
    get_test_work_line_item(
        work=self.clean, amount=Money('100', 'USD'), charge_sales_tax=True)
    self.clean.refresh_from_db()
    self.assertEqual(Money('77', 'USD'), self.clean.workpayment.sales_tax)

  def test_paid_doesnt_update_on_city_tax_rate_change(self):
    self.assertIsNone(self.clean.workpayment.paypal_payout)
    payout = get_successful_payout(
        amount=self.clean.workpayment.get_total_amount())
    self.clean.workpayment.paypal_payout = payout
    self.clean.workpayment.save()
    self.assertTrue(self.clean.workpayment.paid_at())

    self.clean_co.services_tax_rate = 8
    self.clean_co.save()
    # Theoretically the sales tax could be more at this point
    self.assertEqual(
        Money('80', 'USD'), self.clean.workpayment.calc_sales_tax())
    # But since it's already paid out, don't update the sales tax.
    self.clean.workpayment.update_sales_tax()
    self.assertEqual(Money('70', 'USD'), self.clean.workpayment.sales_tax)
