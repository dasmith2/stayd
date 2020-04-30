from datetime import date

from django.utils.dateparse import parse_datetime
from djmoney.money import Money

from guesty.api_examples import (
    REFUND, AUTHORIZATION_HOLD_WITH_REFUND, REFUND_NO_BALANCE_DUE_MONEY,
    EXISTING_PAYMENTS, NON_EXISTING_PAYMENT, PAID_AT, AIRBNB_PAYMENT_SYNC,
    LINKS_TO_STRIPE)
from guesty.sync_payments import sync_payments, fix_payment_does_not_exist
from reservations.models import Payment, AuthorizationHold
from reservations.tests import (
    get_test_reservation, get_test_payment, get_test_credit_card_fee)
from util.channels import AIRBNB, BOOKINGCOM
from util.tests import TestCase
from util.timezone import str_to_tz_dt


class SyncPaymentTests(TestCase):
  def test_refunds_and_payments_timed_and_linked_to_stripe(self):
    res = get_test_reservation(
        should_have_payment_count=1, guesty_id='whatever',
        channel=BOOKINGCOM)
    sync_payments(res, LINKS_TO_STRIPE)

    payment = res.payment_set.first()
    self.assertEqual(
        parse_datetime('2018-10-23T20:23:57.356Z'), payment.paid_at)
    self.assertEqual('5b9058abe0365d00430df56e', payment.channel_manager_id)
    self.assertEqual(
        'ch_1DOWPvCeiXlAlNN1zNv0Yjxv', payment.payment_provider_id)

    refund = payment.refund_set.first()
    self.assertEqual(
        parse_datetime('2018-11-07T15:29:52.255Z'), refund.created_at)
    self.assertEqual('re_1DTsyZCeiXlAlNN1NKLSo1kn', refund.payment_provider_id)
    self.assertEqual('5be304f02aa990003ecdbdb8', refund.channel_manager_id)

  def test_fix_payment_does_not_exist(self):
    """ Real life story. """
    reservation = get_test_reservation(
        should_have_payment_count=2, guesty_id='whatever')
    get_test_payment(  # This one has a slightly wrong paid_at.
        reservation=reservation, cc_last_4='3558', cc_brand='MasterCard',
        amount=Money('829.25', 'USD'),
        paid_at=parse_datetime('2018-10-16T14:39:46.128Z'))
    pay2 = get_test_payment(
        reservation=reservation, cc_last_4='1608', cc_brand='Visa',
        amount=Money('829.25', 'USD'),
        paid_at=parse_datetime('2018-10-16T14:39:46.127Z'))
    pay3 = get_test_payment(
        reservation=reservation, cc_last_4='3558', cc_brand='MasterCard',
        amount=Money('829.25', 'USD'),
        paid_at=parse_datetime('2018-08-11T11:34:03.316Z'))

    self.assertEqual(3, reservation.payment_set.count())

    fix_payment_does_not_exist(reservation, money=NON_EXISTING_PAYMENT)

    self.assertEqual(2, reservation.payment_set.count())
    self.assertEqual(set([pay2, pay3]), set(reservation.payment_set.all()))

  def test_fix_airbnb_problems(self):
    """ Real life story. """
    res = get_test_reservation(
        should_have_payment_count=2, guesty_id='whatever', channel=AIRBNB)
    get_test_payment(
        reservation=res, cc_last_4=None, cc_brand=None,
        amount=Money('2820.27', 'USD'),
        paid_at=parse_datetime('2018-01-01 05:00:00+00:00'))
    get_test_payment(
        reservation=res, cc_last_4=None, cc_brand=None,
        amount=Money('380.73', 'USD'),
        paid_at=parse_datetime('2018-01-01 05:00:00+00:00'))
    get_test_payment(
        reservation=res, cc_last_4=None, cc_brand=None,
        amount=Money('2820.27', 'USD'),
        paid_at=parse_datetime('2018-05-14 06:33:57.253000+00:00'))
    get_test_payment(
        reservation=res, cc_last_4=None, cc_brand=None,
        amount=Money('380.73', 'USD'),
        paid_at=parse_datetime('2018-05-14 06:33:57.227000+00:00'))

    sync_payments(res, AIRBNB_PAYMENT_SYNC)

    self.assertEqual(2, res.payment_set.count())
    res.payment_set.get(
        amount=Money('2820.27', 'USD'), channel_manager_id='blahblahblah',
        paid_at=parse_datetime('2018-05-14 06:33:57.253000+00:00'))
    res.payment_set.get(
        amount=Money('380.73', 'USD'), channel_manager_id='foofoofoo',
        paid_at=parse_datetime('2018-05-14 06:33:57.227000+00:00'))

  def test_fix_identical_payments(self):
    """ Real life story. This tests on EXISTING_PAYMENTS. This import shouldn't
    go up top. It's here, and it's a bit ugly, due to conservative code that
    checks to make sure it's ok to delete something. """
    from stripe.tests import get_test_charge
    reservation = get_test_reservation(
        should_have_payment_count=3, guesty_id='whatever')
    original = get_test_payment(
        reservation=reservation, cc_last_4='1032', cc_brand='MasterCard',
        amount=Money('407.50', 'USD'),
        paid_at=parse_datetime('2018-10-18T17:24:34.903Z'))
    # There is an almost identical payment, but the times aren't supposed to be
    # identical like this.
    duplicate = get_test_payment(
        reservation=reservation, cc_last_4='1032', cc_brand='MasterCard',
        amount=Money('407.50', 'USD'),
        paid_at=parse_datetime('2018-10-18T17:24:34.903Z'))

    # But oh no, charges were already associated with both duplicates!
    charge_1 = get_test_charge(
        cc_last_4='1032', cc_brand='MasterCard',
        amount=Money('407.50', 'USD'),
        payment=original, created=str_to_tz_dt('2018-10-18 18:00'),
        balance_transaction_id='thiiiiiiiings', charge_id='thuuuuungs')
    # Credit card fees should just get deleted. Real ccfees would have come
    # from real Stripe data and would get recreated when the charge is
    # re-attached to a new payment. This test only needs to check that the
    # charge gets re-attached to a new payment.
    get_test_credit_card_fee(payment=original)
    charge_2 = get_test_charge(
        cc_last_4='1032', cc_brand='MasterCard',
        amount=Money('407.50', 'USD'),
        payment=duplicate, created=str_to_tz_dt('2018-10-18 18:00'),
        balance_transaction_id='theeeeeeeengs', charge_id='thzzzzzngs')
    # These should just get deleted.
    get_test_credit_card_fee(payment=duplicate)

    # And actually this time is off by 1/1000 of a second now that I switched
    # to getting the created_at from the payment and not the attempt as I was
    # before.
    get_test_payment(
        reservation=reservation, cc_last_4='1032', cc_brand='MasterCard',
        amount=Money('50.00', 'USD'),
        paid_at=parse_datetime('2018-10-22 20:51:42.694000+00:00'))
    self.assertEqual(3, reservation.payment_set.count())

    sync_payments(reservation, EXISTING_PAYMENTS)

    # It would be 4, but fix_problems() runs automatically now on a synced
    # reservation.
    self.assertEqual(3, reservation.payment_set.count())
    final_payments = [
        reservation.payment_set.get(
            amount=Money('407.50', 'USD'),
            paid_at=parse_datetime('2018-10-18T16:54:12.297Z')),
        reservation.payment_set.get(
            amount=Money('407.50', 'USD'),
            paid_at=parse_datetime('2018-10-18T16:55:01.073Z')),
        reservation.payment_set.get(
            amount=Money('50.00', 'USD'),
            paid_at=parse_datetime('2018-10-22T20:51:42.693Z'))]
    charge_1.refresh_from_db()
    charge_2.refresh_from_db()
    self.assertNotEqual(charge_1.payment, charge_2.payment)
    self.assertTrue(charge_1.payment in final_payments)
    self.assertTrue(charge_2.payment in final_payments)

  def test_paid_at(self):
    reservation = get_test_reservation(
        should_have_payment_count=1, guesty_id='whatever')
    sync_payments(reservation, PAID_AT)
    self.assertEqual(
        date(2018, 6, 17), reservation.payment_set.first().paid_at.date())

  def test_sync_refunds(self):
    reservation = get_test_reservation()
    sync_payments(reservation, REFUND)
    self.assertEqual(2, reservation.payment_set.count())
    pay1, pay2 = list(reservation.payment_set.all().order_by('amount'))
    self.assertEqual(Money('62.53', 'USD'), pay1.amount)
    self.assertEqual(Money('440.23', 'USD'), pay2.amount)
    self.assertEqual(2, pay2.refund_set.count())
    refund1, refund2 = list(pay2.refund_set.all().order_by('amount'))
    self.assertEqual(Money('37.74', 'USD'), refund1.amount)
    self.assertEqual(Money('402.49', 'USD'), refund2.amount)
    self.assertEqual(Money('0', 'USD'), pay2.get_actual_amount())
    reservation.refresh_from_db()
    self.assertEqual(2, reservation.should_have_payment_count)
    self.assertEqual(Money('1', 'USD'), reservation.get_actual_payin())

  def test_sync_auth_hold_with_refunds(self):
    reservation = get_test_reservation()
    sync_payments(reservation, AUTHORIZATION_HOLD_WITH_REFUND)

  def test_sync_cc_info(self):
    reservation = get_test_reservation()
    for i in range(2):
      sync_payments(reservation, REFUND_NO_BALANCE_DUE_MONEY)

    holds = AuthorizationHold.objects.filter(reservation=reservation)
    self.assertEqual(1, holds.count())
    hold = holds.first()
    self.assertEqual('7642', hold.cc_last_4)
    self.assertEqual('Visa', hold.cc_brand)
    self.assertEqual(parse_datetime('2018-08-27T14:24:04.103Z'), hold.paid_at)
    self.assertEqual(Money('300', 'USD'), hold.amount)

    payments = Payment.objects.filter(reservation=reservation).order_by(
        'amount')
    self.assertEqual(2, payments.count())
    [pay1, pay2] = list(payments)

    self.assertEqual('7642', pay1.cc_last_4)
    self.assertEqual('Visa', pay1.cc_brand)
    self.assertEqual(parse_datetime('2018-08-27T14:24:04.104Z'), pay1.paid_at)
    self.assertEqual(Money('193.27', 'USD'), pay1.amount)

    self.assertEqual('1032', pay2.cc_last_4)
    self.assertEqual('MasterCard', pay2.cc_brand)
    self.assertEqual(parse_datetime('2018-08-27T14:31:37.251Z'), pay2.paid_at)
    self.assertEqual(Money('386.54', 'USD'), pay2.amount)
