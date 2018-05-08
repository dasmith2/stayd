from datetime import datetime, timedelta, date

from django.test import TestCase
from django.utils.timezone import make_aware
from djmoney.money import Money
from owner_payouts.models import (
    ReservationToPayout, ReservationAdjustmentToPayout, OwnerPayout,
    PayoutRule)
from pays.paypal_api import MockPaypalApi
from reservations.models import ReservationAdjustment
from reservations.tests import get_test_reservation


class UpdatePayoutTests(TestCase):
  def get_test_reservation_to_payout(self, **kwargs):
    reservation = get_test_reservation(True, **kwargs)
    PayoutRule.objects.get_or_create(
        percent=.95, days_after_payment=2,
        owner=reservation.listing.rental.owner,
        goes_into_effect=days_delta(-10))
    reservation.listing.rental.owner.save()
    return ReservationToPayout.objects.get_for_reservation(reservation)

  def test_when_did_we_get_paid(self):
    check_in = days_delta(-5)
    res = self.get_test_reservation_to_payout(
        is_paid_in=True,
        check_in=check_in,
        check_out=days_delta(-3))
    self.assertEqual(
        check_in + timedelta(days=1), res.reservation.when_did_we_get_paid())

  def test_not_paid_in_yet(self):
    res = self.get_test_reservation_to_payout(
        is_paid_in=False,
        check_in=days_delta(-5),
        check_out=days_delta(-3))
    res.update_payout()
    self.assertIsNone(res.payout)

  def test_before_goes_into_effect(self):
    res = self.get_test_reservation_to_payout(
        is_paid_in=False,
        check_in=days_delta(-5),
        check_out=days_delta(-3))
    payout_rule = PayoutRule.objects.get(owner=res.get_listing().rental.owner)
    payout_rule.goes_into_effect = make_aware(datetime.now())
    payout_rule.save()
    res.update_payout()
    self.assertIsNone(res.payout)

  def test_no_payout_yet_should_pay_in_future(self):
    res = self.get_test_reservation_to_payout(
        check_in=days_delta(-1),
        check_out=days_delta(1),
        total_payin=Money(123, 'USD'))
    res.update_payout()

    payout = OwnerPayout.objects.get(id=res.payout.id)

    self.assertEqual(Money(.95 * 123, 'USD'), payout.amount)
    # get_test_reservations sets days_after_payment to 2
    self.assertEqual(
        payout.when_should, (
            res.reservation.when_did_we_get_paid() + timedelta(days=2)).date())
    self.assertEqual(
        payout.who_to_pay.email, res.get_listing().rental.owner.email)
    self.assertTrue(payout.public_id)

  def test_no_payout_yet_should_pay_in_past_pays_today(self):
    res = self.get_test_reservation_to_payout(
        check_in=days_delta(-10),
        check_out=days_delta(-8),
        total_payin=Money(321, 'USD'))
    res.update_payout()

    payout = OwnerPayout.objects.get(id=res.payout.id)

    self.assertEqual(payout.when_should, date.today())

  def test_multiple_reservations(self):
    res1 = self.get_test_reservation_to_payout(
        check_in=days_delta(-1),
        check_out=days_delta(1),
        total_payin=Money(321, 'USD'))
    res1.update_payout()
    res2 = self.get_test_reservation_to_payout(
        check_in=days_delta(-1),
        check_out=days_delta(1),
        total_payin=Money(123, 'USD'))
    res2_rental = res2.get_listing().rental
    res2_rental.owner = res1.get_listing().rental.owner
    res2_rental.save()
    res2.update_payout()
    if not res2.payout:
      raise Exception(res2.explain_why_no_payout())

    payout = OwnerPayout.objects.get(id=res1.payout.id)

    self.assertEqual(payout.id, res2.payout.id)
    self.assertEqual(.95 * Money(321 + 123, 'USD'), payout.amount)

  def test_existing_unpaid_payout_amount_changes(self):
    res1 = self.get_test_reservation_to_payout(
        check_in=days_delta(-1),
        check_out=days_delta(1),
        total_payin=Money(321, 'USD'))
    res1.update_payout()

    res1.reservation.total_payin = Money(333, 'USD')
    res1.reservation.save()
    res1.update_payout()

    payout = OwnerPayout.objects.get(id=res1.payout.id)

    self.assertEqual(.95 * Money(333, 'USD'), payout.amount)

  def test_existing_paid_payout_amount_does_not_change(self):
    res1 = self.get_test_reservation_to_payout(
        check_in=days_delta(-10),
        check_out=days_delta(-5),
        total_payin=Money(321, 'USD'))
    res1.update_payout()

    payout = OwnerPayout.objects.get(id=res1.payout.id)
    payout.paypal_api = MockPaypalApi()
    payout.send()

    res1.total_payin = Money(333, 'USD')
    res1.update_payout()

    payout = OwnerPayout.objects.get(id=res1.payout.id)

    self.assertEqual(Money(.95 * 321, 'USD'), payout.amount)

  def test_adding_adjustments(self):
    a_150_bucks = Money(150, 'USD')
    res1 = self.get_test_reservation_to_payout(
        check_in=days_delta(-2),
        check_out=days_delta(-1),
        total_payin=a_150_bucks)
    res1.update_payout()

    a_100_bucks = Money(100, 'USD')
    res2 = self.get_test_reservation_to_payout(
        check_in=days_delta(-1),
        check_out=days_delta(-0),
        total_payin=a_100_bucks)

    res2_rental = res2.get_listing().rental
    res2_rental.owner = res1.get_listing().rental.owner
    res2_rental.save()
    res2.update_payout()

    ra = ReservationAdjustment.objects.create(
        listing=res1.get_listing(),
        amount=Money(-60, 'USD'),
        reason='Walk it off')
    # The first adjustment has a ReservationAdjustmentToPayout of these but
    # with a null payout
    ReservationAdjustmentToPayout.objects.create(reservation_adjustment=ra)
    ReservationAdjustment.objects.create(
        listing=res1.get_listing(),
        amount=Money(-110, 'USD'),
        reason='Hot mess express')
    # The second adjustment doesn't even have a ReservationAdjustmentToPayout

    ReservationAdjustmentToPayout.objects.assign_adjustments()

    payout1 = OwnerPayout.objects.get(id=res1.payout.id)
    self.assertEqual(Money(.95 * (150 - 110), 'USD'), payout1.amount)
    payout2 = OwnerPayout.objects.get(id=res2.payout.id)
    self.assertEqual(Money(.95 * (100 - 60), 'USD'), payout2.amount)


def days_delta(delta):
  return make_aware(datetime.now() + timedelta(days=delta))
