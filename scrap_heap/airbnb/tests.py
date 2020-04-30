from datetime import date

from djmoney.money import Money

from airbnb.models import (
    Payout, ReservationPayout, missing_reservations, RawUpload)
from reservations.tests.tests import get_test_reservation
from util.random_string import random_string
from util.tests import TestCase
from xxero.tests.test_transactions import get_test_transaction


def get_test_payout(**kwargs):
  return Payout.objects.create(
      date=kwargs.get('date', date(2019, 1, 1)),
      amount=kwargs.get('amount', Money('10', 'USD')),
      note=kwargs.get('note', 'Transfer to *****8228'),
      transaction=kwargs.get('transaction', None))


def get_test_reservation_payout(**kwargs):
  payout = kwargs.get('payout', None)
  if not payout:
    payout = get_test_payout(**kwargs)
  return ReservationPayout.objects.create(
      payout=payout,
      channel_id=kwargs.get('channel_id', random_string(7)),
      amount=kwargs.get('amount', Money('10', 'USD')))


class AirbnbTests(TestCase):
  def test_handle_upload_airbnb_csv(self):
    """ The same reservation can be paid out in more than one payout, and one
    payout may have more than one reservation. """
    # Let's say we don't have HMHHW5PC29 in our database.
    csv_text = (
        '\ufeffDate,Type,Confirmation Code,Start Date,Nights,'
        'Guest,Listing,Details,Reference,Currency,Amount,Paid Out,Host Fee,'
        'Cleaning Fee\n'
        # row_1
        '2/10/2019,Payout,,,,,,Transfer to *****8228,,,,'
        '50.44,,\n'
        # row_2. Note that HMPY33PDYA is paid out in 2 spots, row_1 and row_6
        '1/30/2019,Reservation,HMPY33PDYA,1/29/2019,20,'
        'Christina Kemp,AMAZING 2BR/1BA with Yard!! Min from NYC! Sleeps 8,'
        ',,,50.44,,1.56,4.18\n'
        # row_3. Note that this payout has 2 reservations in it.
        '2/5/2019,Payout,,,,,,Transfer to *****8228,,,,'
        '1815.74,,\n'
        # row_4
        '2/5/2019,Reservation,HMDBDR24EX,2/4/2019,7,Xuchao Ang,'
        'AWESOME 2BR/2BA **2 STOPS FROM NYC**,,,,1040.71,,32.19,'
        '100\n'
        # row_5
        '2/5/2019,Reservation,HMHHW5PC29,2/4/2019,7,'
        'Carlo Salazar,GORGEOUS 2BR/1BA in Trendy JC! Min to NY! Sleeps 8,'
        ',,,775.03,,23.97,100\n'
        # row_6
        '1/30/2019,Payout,,,,,,Transfer to *****8228,,,,'
        '1028.16,,\n'
        # row_7
        '1/30/2019,Reservation,HMPY33PDYA,1/29/2019,20,'
        'Christina Kemp,AMAZING 2BR/1BA with Yard!! Min from NYC! Sleeps 8,'
        ',,,1155.27,,35.73,95.82\n'
        # row_8
        '1/26/2019,Resolution Adjustment,,,,,,'
        'Resolution adjustment for resolution 10654307,,,-4.99,,,\n'
        # row_9
        '12/27/2018,Resolution Payout,,,,,,'
        'Resolution payout for resolution 10180204,,,25,,,\n'
        # row_10
        '12/20/2018,Tax Withholding,HMN5QYBRTP,12/19/2018,3,'
        'Stanislas Wierzbicki,'
        'AMAZING 2BR/1BA with Yard!! Min from NYC! Sleeps 8,,,,-147.12,'
        ',,\n'
        # row_11
        '03/07/2019,Cancellation Fee Refund,,,,,,'
        'Refund of cancellation fee for reservation HMNE8D4JZ3,,'
        'USD,43.00,,,\n')

    raw = RawUpload.objects.create(text=csv_text)
    self.assertFalse(raw.handled_at)
    raw.handle()
    raw.refresh_from_db()
    self.assertTrue(raw.handled_at)

    self.assertEqual(3, Payout.objects.count())
    [payout_1, payout_2, payout_3] = Payout.objects.order_by('-date')

    self.assertEqual(date(2019, 2, 10), payout_1.date)
    self.assertEqual(Money('50.44', 'USD'), payout_1.amount)
    self.assertEqual('Transfer to *****8228', payout_1.note)
    self.assertEqual(1, payout_1.reservationpayout_set.count())
    payout_1.reservationpayout_set.get(
        channel_id='HMPY33PDYA', amount=Money('50.44', 'USD'))

    self.assertEqual(date(2019, 2, 5), payout_2.date)
    self.assertEqual(2, payout_2.reservationpayout_set.count())

    self.assertEqual(date(2019, 1, 30), payout_3.date)
    payout_3.reservationpayout_set.get(
        channel_id='HMPY33PDYA', amount=Money('1155.27', 'USD'))
    self.assertEqual(3, payout_3.resolutionadjustment_set.count())
    payout_3.resolutionadjustment_set.get(
        date=date(2019, 1, 26), amount=Money('-4.99', 'USD'),
        note='Resolution adjustment for resolution 10654307')
    payout_3.resolutionadjustment_set.get(
        date=date(2018, 12, 27), amount=Money('25', 'USD'),
        note='Resolution payout for resolution 10180204')
    payout_3.resolutionadjustment_set.get(
        date=date(2019, 3, 7), amount=Money('43', 'USD'),
        note='Refund of cancellation fee for reservation HMNE8D4JZ3')
    self.assertEqual(1, payout_3.other_set.count())
    payout_3.other_set.get(
        name='Tax Withholding', channel_id='HMN5QYBRTP',
        amount=Money('-147.12', 'USD'))

  def test_match_payouts_to_transactions(self):
    match_pay = get_test_payout(
        date=date(2019, 1, 1), amount=Money('100.00', 'USD'))
    reservation_1 = get_test_reservation(channel_id='justOk')
    get_test_reservation_payout(
        payout=match_pay, channel_id='justOk', reservation=reservation_1)
    reservation_2 = get_test_reservation(channel_id='whatever')
    get_test_reservation_payout(
        payout=match_pay, channel_id='whatever', reservation=reservation_2)
    get_test_reservation_payout(
        payout=match_pay, channel_id='we_dont_have_this_reservation',
        reservation=reservation_2)

    # The transactions typically show up a few days after Airbnb says they sent
    # it.
    match_transact = get_test_transaction(
        amount=Money('100.00', 'USD'), when=date(2019, 1, 2))

    transact_already = get_test_transaction(
        date=date(2019, 2, 3), amount=Money('333.33', 'USD'))
    has_transact_already = get_test_payout(
        date=date(2019, 2, 1), amount=Money('333.33', 'USD'),
        transaction=transact_already)
    get_test_transaction(  # should_not_match
        amount=Money('333.33', 'USD'), when=date(2019, 2, 2))

    for i in range(2):
      Payout.objects.match_payouts_to_transactions()

    match_pay.refresh_from_db()
    self.assertEqual(match_transact, match_pay.transaction)
    self.assertEqual(
        [reservation_1, reservation_2],
        list(match_transact.reservations.order_by('pk')))
    has_transact_already.refresh_from_db()
    self.assertEqual(transact_already, has_transact_already.transaction)

    self.assertEqual(['we_dont_have_this_reservation'], missing_reservations())
