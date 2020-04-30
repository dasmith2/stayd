from decimal import Decimal
from unittest.mock import Mock, call
from uuid import uuid4 as random_uuid

from django.shortcuts import reverse
from djmoney.money import Money

from errors.models import Notifier
from guesty.api_examples import RESERVATION
from reservations.tests import (
    get_test_payment, get_test_refund as get_test_reservation_refund,
    get_test_reservation, get_test_resolution_category)
from stripe.api import API
from stripe.api_examples import (
    PAYOUT, PAYOUTS, BALANCE_TRANSACTION, BALANCE_TRANSACTIONS, CHARGE,
    FAILED_CHARGE, CHARGE_WITH_REFUND, REFUND, CHARGE_WITH_WEIRD_SOURCE)
from stripe.models import (
    Payout, BalanceTransaction, Charge, Refund, Fee, sync_all,
    unlinked_charges, unlinked_charges_table,
    alert_unlinked_charges_background, handle_resolve_unlinked_charge_post)
from util.permission import ACCOUNTANT
from util.random_string import random_string
from util.table import Cell
from util.tests import TestCase
from util.timezone import ts_to_utc_dt, str_to_tz_dt


def get_test_payout(**kwargs):
  arrival_date = kwargs.get('arrival_date', str_to_tz_dt('2018-05-15 11:00'))
  return Payout.objects.create(
      payout_id=kwargs.get('payout_id', 'bingbangboing'),
      amount=kwargs.get('amount', Money('10.0', 'USD')),
      arrival_date=arrival_date,
      balance_transactions_synced_at=kwargs.get(
          'balance_transactions_synced_at', None))


def get_test_balance_transaction(**kwargs):
  balance_transaction_id = kwargs.get(
      'balance_transaction_id', str(random_uuid()))
  amount = kwargs.get('amount', Decimal('10.0'))
  if isinstance(amount, Money):
    amount = amount.amount
  return BalanceTransaction.objects.create(
      balance_transaction_id=balance_transaction_id,
      payout=kwargs.get('payout', None),
      amount=amount,
      total_fees=kwargs.get('total_fees', Decimal('1.0')),
      net=kwargs.get('net', Decimal('9.0')),
      currency=kwargs.get('currency', 'USD'),
      ttype=kwargs.get('ttype', 'payout'))


def get_test_charge(**kwargs):
  balance_transaction = kwargs.get('balance_transaction', None)
  if not balance_transaction:
    balance_transaction = get_test_balance_transaction(**kwargs)
  return Charge.objects.create(
      charge_id=kwargs.get('charge_id', 'choorgebuydee'),
      balance_transaction=balance_transaction,
      amount=kwargs.get('amount', Money('12.34', 'USD')),
      refunds_synced_at=kwargs.get('refunds_synced_at', None),
      amount_refunded=kwargs.get('amount_refunded', Money('0.0', 'USD')),
      created=kwargs.get('created', str_to_tz_dt('2018-05-15 00:00')),
      cc_last_4=kwargs.get('cc_last_4', '5678'),
      cc_brand=kwargs.get('cc_brand', 'Masterborg'),
      dispute_id=kwargs.get('dispute_id', None),
      payment=kwargs.get('payment', None))


def get_test_fee(**kwargs):
  balance_transaction = kwargs.get('balance_transaction', None)
  if not balance_transaction:
    balance_transaction = get_test_balance_transaction(**kwargs)
  return Fee.objects.create(
      balance_transaction=balance_transaction,
      description=kwargs.get('description', 'Monstercardx fee'),
      amount=kwargs.get('amount', Money('12.34', 'USD')))


def get_test_refund(**kwargs):
  charge = kwargs.get('charge', None)
  if not charge:
    charge = get_test_charge(**kwargs)
  balance_transaction = kwargs.get('balance_transaction', None)
  if not balance_transaction:
    balance_transaction = get_test_balance_transaction(**kwargs)
  return Refund.objects.create(
      refund_id=kwargs.get('refund_id', random_string()),
      charge=charge,
      balance_transaction=balance_transaction,
      amount=kwargs.get('amount', Money('26', 'USD')),
      reservation_refund=kwargs.get('reservation_refund', None))


class ErroneousChargeTests(TestCase):
  def setUp(self):
    super().setUp()
    payment = get_test_payment(
        amount=Money('123.00', 'USD'),
        paid_at=str_to_tz_dt('2018-12-25 12:00'), cc_last_4='4321',
        cc_brand='Blargincard', payment_provider_id='aaa',
        full_name='Gary Guest', guesty_id='kwkwkwkw')
    get_test_charge(
        charge_id='aaa', amount=Money('123.00', 'USD'),
        created=str_to_tz_dt('2018-12-25 12:00'), cc_last_4='4321',
        cc_brand='Blargincard', payment=payment)
    self.duplicate = get_test_charge(
        charge_id='bbb', amount=Money('123.00', 'USD'),
        created=str_to_tz_dt('2018-12-25 12:00'), cc_last_4='4321',
        cc_brand='Blargincard')

  def test_unlinked_charges(self):
    self.assertEqual(
        [self.duplicate],
        list(unlinked_charges(nnow=str_to_tz_dt('2019-01-01'))))
    self.duplicate.amount_refunded = Money('123.00', 'USD')
    self.duplicate.save()
    self.assertEqual(
        [], list(unlinked_charges(nnow=str_to_tz_dt('2019-01-01'))))

  def test_handle_resolve_unlinked_charge_post(self):
    unlinked_count = len(
        list(unlinked_charges(nnow=str_to_tz_dt('2019-01-01'))))
    self.assertEquals(1, unlinked_count)

    get_test_resolution_category(name='Actually paid in')
    request_post = {
        'resolution_category': 'Actually paid in', 'notes': 'Stuff.'}
    self.assertTrue(handle_resolve_unlinked_charge_post(
        request_post, self.duplicate))

    unlinked_count = len(
        list(unlinked_charges(nnow=str_to_tz_dt('2019-01-01'))))
    self.assertEquals(0, unlinked_count)

  def test_unlinked_charges_table(self):
    table = unlinked_charges_table(nnow=str_to_tz_dt('2019-01-01'))
    expected_headers = [
        'Resolve me', 'Amount', 'When', 'Stripe Charge ID', 'Last 4',
        'CC brand', 'Identical payment found in reservation']
    self.assertEqual(expected_headers, table.headers)
    self.assertEqual(1, len(table.rows))
    url = 'https://app.guesty.com/reservations/kwkwkwkw/guests'
    resolve_cell = Cell('Resolve me', url=reverse(
        'resolve_unlinked_charge',
        kwargs={'charge_id': self.duplicate.pk}))
    expected_cells = [
        resolve_cell, Money('123.00', 'USD'), str_to_tz_dt('2018-12-25 12:00'),
        'bbb', '4321', 'Blargincard', Cell('Gary Guest', url=url)]
    self.assertEqual(expected_cells, table.rows[0].cells)

  def test_alert_unlinked_charges_background(self):
    notifier = Mock(spec=Notifier)
    alert_unlinked_charges_background(
        nnow=str_to_tz_dt('2019-01-01'), notifier=notifier)
    self.assertEqual(1, len(notifier.notify.call_args_list))


class ChargeTests(TestCase):
  def test_unlink_siblings_of_unmatched(self):
    get_test_charge(  # unmatched
        amount=Money('78.78', 'USD'), created=str_to_tz_dt('2018-12-02 01:00'),
        balance_transaction_id='a', charge_id='a')
    sibling = get_test_charge(
        amount=Money('78.78', 'USD'), created=str_to_tz_dt('2018-12-01 00:00'),
        payment=get_test_payment(amount=Money('78.78', 'USD')),
        balance_transaction_id='b', charge_id='b')
    non_sibling = get_test_charge(
        amount=Money('99.99', 'USD'), created=str_to_tz_dt('2018-12-02 01:00'),
        payment=get_test_payment(amount=Money('99.99', 'USD')),
        balance_transaction_id='c', charge_id='c')

    self.assertIsNotNone(sibling.payment)
    self.assertIsNotNone(non_sibling.payment)

    Charge.objects.unlink_siblings_of_unmatched()

    sibling.refresh_from_db()
    non_sibling.refresh_from_db()
    self.assertIsNone(sibling.payment)
    self.assertIsNotNone(non_sibling.payment)

  def test_sync_almost_matched_reservations(self):
    res = get_test_reservation(guesty_id='deep_fried')
    get_test_payment(amount=Money('88.33', 'USD'), reservation=res)
    get_test_charge(amount=Money('88.33', 'USD'))
    sync = Mock()
    sync.api.get_one.return_value = RESERVATION
    Charge.objects.sync_almost_matched_reservations(sync)
    self.assertEqual(
        [call('Reservation', 'deep_fried')], sync.api.get_one.call_args_list)
    self.assertEqual([call(RESERVATION)], sync.sync_reservation.call_args_list)

  def test_match_charges_to_payments(self):
    get_test_payment(  # Different amount
        cc_last_4='4444', cc_brand='Monstercardx',
        amount=Money('555.55', 'USD'))
    get_test_payment(  # Different last 4
        cc_last_4='5555', cc_brand='Monstercardx',
        amount=Money('444.44', 'USD'))
    get_test_payment(  # Different cc brand
        cc_last_4='4444', cc_brand='Saintmx',
        amount=Money('444.44', 'USD'))
    refunded = get_test_payment(  # Has refunds
        cc_last_4='4444', cc_brand='Monstercardx',
        amount=Money('444.44', 'USD'))
    get_test_reservation_refund(
        payment=refunded, amount=Money('111.11', 'USD'))
    has_charge_already = get_test_payment(
        cc_last_4='4444', cc_brand='Monstercardx',
        amount=Money('444.44', 'USD'))
    get_test_charge(
        payment=has_charge_already,
        balance_transaction_id='whaaaaatever', charge_id='whuuuuutaver')

    the_right_payment = get_test_payment(
        cc_last_4='4444', cc_brand='Monstercardx',
        amount=Money('444.44', 'USD'))

    too_old_for_matches = get_test_charge(
        cc_last_4='4444', cc_brand='Monstercardx',
        amount=Money('444.44', 'USD'),
        payment=None, created=str_to_tz_dt('2018-04-01 00:00'),
        balance_transaction_id='stuuuuuuuuf', charge_id='staaaaaaaaf')
    get_test_fee(
        balance_transaction=too_old_for_matches.balance_transaction,
        amount=Money('5.55', 'USD'), description='I fee you!')
    charge_1 = get_test_charge(
        cc_last_4='4444', cc_brand='Monstercardx',
        amount=Money('444.44', 'USD'),
        payment=None, created=str_to_tz_dt('2018-04-02 00:00'),
        balance_transaction_id='thiiiiiiiings', charge_id='thuuuuungs')
    get_test_fee(
        balance_transaction=charge_1.balance_transaction,
        amount=Money('3.33', 'USD'), description='You get this fee now!')

    for i in range(2):
      Charge.objects.match_charges_to_payments(
          str_to_tz_dt('2018-04-02 00:00'))

    too_old_for_matches.refresh_from_db()
    self.assertIsNone(too_old_for_matches.payment)
    charge_1.refresh_from_db()
    self.assertEqual(the_right_payment, charge_1.payment)
    cc_fees = the_right_payment.creditcardfee_set.all()
    self.assertEqual(1, cc_fees.count())
    cc_fee = cc_fees.first()
    self.assertEqual('You get this fee now!', cc_fee.description)
    self.assertEqual(Money('3.33', 'USD'), cc_fee.amount)

  def test_charge_already_matched_fees_turn_into_credit_card_fees(self):
    """ Charges have fees, but we find out about the fees in the balance
    transaction. So if we manage to have all the fees, charges, and balance
    transactions in place before we call charge.match_to_payment, then the
    payment it matches to will get all the fees. Cool. But what if we match the
    charge to the payment and THEN we find out about the Fees. """
    balance_transaction = get_test_balance_transaction()
    payment = get_test_payment()
    get_test_charge(payment=payment, balance_transaction=balance_transaction)
    self.assertEqual(0, payment.creditcardfee_set.count())
    get_test_fee(
        balance_transaction=balance_transaction, description='Stuff.',
        amount=Money('1.23', 'USD'))
    payment.creditcardfee_set.get(
        payment=payment, description='Stuff.', amount=Money('1.23', 'USD'))

  def test_match_charges_to_payments_will_ignore_refunds_if_necessary(self):
    refunded = get_test_payment(
        cc_last_4='4444', cc_brand='Monstercardx',
        amount=Money('444.44', 'USD'))
    get_test_reservation_refund(
        payment=refunded, amount=Money('111.11', 'USD'))
    charge_1 = get_test_charge(
        cc_last_4='4444', cc_brand='Monstercardx',
        amount=Money('444.44', 'USD'),
        payment=None, created=str_to_tz_dt('2018-04-02 00:00'),
        balance_transaction_id='thiiiiiiiings', charge_id='thuuuuungs')
    Charge.objects.match_charges_to_payments(
        str_to_tz_dt('2018-04-02 00:00'))
    charge_1.refresh_from_db()
    self.assertEqual(refunded, charge_1.payment)

  def test_match_charges_sibling_payments(self):
    reservation = get_test_reservation()
    no_cc_right_amount = get_test_payment(
        reservation=reservation, cc_last_4=None, cc_brand=None,
        amount=Money('444.44', 'USD'))
    get_test_payment(  # right_cc_wrong_amount
        reservation=reservation, cc_last_4='7777',
        cc_brand='Monstercardx', amount=Money('555.55', 'USD'))

    wrong_cc_last_4 = get_test_charge(
        cc_last_4='8888', cc_brand='Monstercardx',
        amount=Money('444.44', 'USD'),
        payment=None, created=str_to_tz_dt('2018-04-02 00:00'),
        balance_transaction_id='werlsnk',
        charge_id='dnslekng')
    wrong_cc_last_4.match_to_payment()
    should_match = get_test_charge(
        cc_last_4='7777', cc_brand='Monstercardx',
        amount=Money('444.44', 'USD'),
        payment=None, created=str_to_tz_dt('2018-04-02 00:00'),
        balance_transaction_id='thiiiiiiiings',
        charge_id='thuuuuungs')
    should_match.match_to_payment()

    self.assertIsNone(wrong_cc_last_4.payment)
    self.assertEqual(no_cc_right_amount, should_match.payment)

  def test_match_charges_manual_payments(self):
    reservation = get_test_reservation()
    payment = get_test_payment(
        reservation=reservation, cc_last_4=None, cc_brand=None,
        amount=Money('444.44', 'USD'),
        paid_at=str_to_tz_dt('2018-12-01 12:34'))
    charge = get_test_charge(
        cc_last_4='8888', cc_brand='Monstercardx',
        amount=Money('444.44', 'USD'),
        payment=None, created=str_to_tz_dt('2018-12-01 10:01'),
        balance_transaction_id='werlsnk',
        charge_id='dnslekng')
    charge.match_to_payment()
    self.assertEqual(payment, charge.payment)


class PayoutTests(TestCase):
  def test_sync_payouts(self):
    api = Mock(spec=API)
    api.get_payouts.return_value = PAYOUTS['data']
    for i in range(3):
      Payout.objects.sync(None, api)
    self.assertEqual(2, Payout.objects.count())
    payout1 = Payout.objects.first()
    self.assertEqual('po_1DRW4qCeiXlAlNN1xdw7tWmP', payout1.payout_id)
    self.assertEqual(Money('-.10', 'USD'), payout1.amount)
    self.assertEqual(ts_to_utc_dt(1541116800), payout1.arrival_date)
    self.assertIsNone(payout1.balance_transactions_synced_at)


class BalanceTransactionTests(TestCase):
  def get_api(self):
    api = Mock(spec=API)
    api.get_balance_transactions.return_value = BALANCE_TRANSACTIONS['data']
    api.get_charges.return_value = [CHARGE, FAILED_CHARGE]
    return api

  def do_test(self, payout):
    payout.refresh_from_db()
    self.assertIsNotNone(payout.balance_transactions_synced_at)

    bt = BalanceTransaction.objects.get(
        balance_transaction_id='txn_1DR4g1CeiXlAlNN1A6TRDYbI')
    self.assertEqual(payout, bt.payout)
    self.assertEqual(Decimal('1117.31'), bt.amount)
    self.assertEqual(Decimal('36.05'), bt.total_fees)
    self.assertEqual(Decimal('1081.26'), bt.net)
    self.assertEqual('USD', bt.currency)
    self.assertEqual('charge', bt.ttype)

    fees = bt.fee_set.all()
    self.assertEqual(2, fees.count())
    fee1, fee2 = list(fees)
    self.assertEqual('Guesty application fee', fee1.description)
    self.assertEqual(Money('3.35', 'USD'), fee1.amount)
    self.assertEqual('Stripe processing fees', fee2.description)
    self.assertEqual(Money('32.70', 'USD'), fee2.amount)

    charge = Charge.objects.get(charge_id='ch_1DR4fzCeiXlAlNN1Y5Bv9ely')
    self.assertEqual(bt, charge.balance_transaction)
    self.assertEqual(Money('1117.31', 'USD'), charge.amount)
    self.assertEqual(ts_to_utc_dt(1540934583), charge.created)
    self.assertEqual('1364', charge.cc_last_4)
    self.assertEqual('Visa', charge.cc_brand)
    self.assertEqual('Kathrin Büttner 50 Regent 209', charge.description)

  def test_sync_payout_first(self):
    api = self.get_api()

    payout = get_test_payout(balance_transactions_synced_at=None)
    for i in range(2):
      Payout.objects.sync_balance_transactions(api)

    for i in range(2):
      Charge.objects.sync(None, api)

    self.do_test(payout)

  def test_sync_charge_first(self):
    api = self.get_api()

    api.get_balance_transaction.return_value = BALANCE_TRANSACTION
    for i in range(2):
      Charge.objects.sync(None, api)

    payout = get_test_payout()
    for i in range(2):
      Payout.objects.sync_balance_transactions(api)

    self.do_test(payout)

  def test_sync_all(self):
    api = self.get_api()
    api.get_payouts.return_value = [PAYOUT]

    for i in range(2):
      sync_all(api=api)

    self.do_test(Payout.objects.first())


class ChargeWithWeirdSourceTests(TestCase):
  def test_sync_charge_with_weird_source(self):
    api = Mock(spec=API)
    api.get_charges.return_value = [CHARGE_WITH_WEIRD_SOURCE]
    get_test_payment(
        payment_provider_id='ch_1FWVNJCeiXlAlNN12DRp8ds5')
    get_test_balance_transaction(
        balance_transaction_id='txn_1FWVNKCeiXlAlNN1gznsq00u')
    Charge.objects.sync(since=None, api=api)
    charge = Charge.objects.first()
    self.assertEqual('2401', charge.cc_last_4)
    self.assertEqual('MasterCard', charge.cc_brand)


class RefundTests(TestCase):
  def test_sync_charge_and_refund(self):
    """ This tests, among other things, the channel manager syncs a payment and
    refund first, then we sync a charge and stripe refund, and they're linked.
    """
    api = Mock(spec=API)
    api.get_charges.return_value = [CHARGE_WITH_REFUND]
    api.get_refunds.return_value = [REFUND]

    reservation_refund = get_test_reservation_refund(
        payment_provider_id='re_1DTsyZCeiXlAlNN1NKLSo1kn')
    payment = get_test_payment(
        payment_provider_id='ch_1DOWPvCeiXlAlNN1zNv0Yjxv')

    charge_bt = get_test_balance_transaction(
        balance_transaction_id='txn_1DOWPwCeiXlAlNN1cFDD3KPO')
    refund_bt = get_test_balance_transaction(
        balance_transaction_id='txn_1DTsyZCeiXlAlNN1GLSRvftt')

    Charge.objects.sync(None, api)
    charge = Charge.objects.first()
    self.assertIsNone(charge.refunds_synced_at)
    self.assertEqual(Money('327.78', 'USD'), charge.amount_refunded)
    self.assertEqual(charge_bt, charge.balance_transaction)
    self.assertEqual(payment, charge.payment)

    for i in range(2):
      Charge.objects.sync_refunds(api)
    charge.refresh_from_db()
    self.assertIsNotNone(charge.refunds_synced_at)

    self.assertEqual(1, Refund.objects.count())
    refund = Refund.objects.first()
    self.assertEqual('re_1DTsyZCeiXlAlNN1NKLSo1kn', refund.refund_id)
    self.assertEqual(charge, refund.charge)
    self.assertEqual(refund_bt, refund.balance_transaction)
    self.assertEqual(Money('327.78', 'USD'), refund.amount)
    self.assertEqual(reservation_refund, refund.reservation_refund)

  def test_save_links_reservation_objects(self):
    """ This tests charge and refund exist first, then some channel manager
    syncs a payment and refund, and they're linked. """
    charge = get_test_charge(charge_id='ch_1DOWPvCeiXlAlNN1zNv0Yjxv')
    refund = get_test_refund(refund_id='re_1DTsyZCeiXlAlNN1NKLSo1kn')

    payment = get_test_payment(
        payment_provider_id='ch_1DOWPvCeiXlAlNN1zNv0Yjxv')
    reservation_refund = get_test_reservation_refund(
        payment_provider_id='re_1DTsyZCeiXlAlNN1NKLSo1kn')

    refund.refresh_from_db()
    charge.refresh_from_db()
    self.assertEqual(reservation_refund, refund.reservation_refund)
    self.assertEqual(payment, charge.payment)


class ViewTests(TestCase):
  def test_charge_to_reservation(self):
    get_test_charge(
        payment=get_test_payment(channel_id='doofus'),
        created=str_to_tz_dt('2018-12-02 12:00'))
    self.login(group=ACCOUNTANT)
    url = reverse('charge_to_reservation', kwargs={
        'from_date_str': '12-01-2018', 'to_date_str': '01-01-2019'})
    self.assert_get_contains(url, 'doofus')
