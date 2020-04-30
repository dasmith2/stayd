from datetime import date
from decimal import Decimal

from djmoney.money import Money

from rentals.tests import (
    get_test_owner, get_test_building, get_test_rental)
from reservations.models import ReservationLineItem, KNOWN_LINE_ITEM_NAMES
from reservations.tests.tests import get_test_reservation, get_test_payment
from stats.models.stale import Stale
from stats.models.stats import Stats, MONTH
from util.tests import TestCase
from util.timezone import str_to_tz_dt


class ComboRentalComputerTests(TestCase):
  def test(self):
    owner = get_test_owner()
    building = get_test_building(owner=owner)
    atom_1 = get_test_rental(
        building=building, nickname='atom 1', accommodates=4)
    atom_2 = get_test_rental(
        building=building, nickname='atom 2', accommodates=6)
    combo = get_test_rental(building=building, is_combo_of=[atom_1, atom_2])
    reservation = get_test_reservation(
        rental=combo, check_in=str_to_tz_dt('2018-12-15 16:00'),
        check_out=str_to_tz_dt('2018-12-16 11:00'),
        ideal_payin=Money('100', 'USD'))
    ReservationLineItem.objects.create(
        name=KNOWN_LINE_ITEM_NAMES.RENT,
        value=Money(100.0, 'USD'),
        reservation=reservation)
    get_test_payment(
        reservation=reservation,
        amount=Money('100.0', 'USD'),
        paid_at=str_to_tz_dt('2018-12-17 00:00'))

    Stale.objects.mark_stale_due_to_reservation(reservation)
    Stale.objects.fix()

    self.assertEqual(0, Stats.objects.filter(rental=combo).count())
    self.assertEqual(Decimal('40'), Stats.objects.get(
        rental=atom_1, interval=MONTH,
        from_date=date(2018, 12, 1)).rooms_revenue)
    self.assertEqual(Decimal('60'), Stats.objects.get(
        rental=atom_2, interval=MONTH,
        from_date=date(2018, 12, 1)).rooms_revenue)
    self.assertEqual(Decimal('100'), Stats.objects.get(
        building=building, interval=MONTH,
        from_date=date(2018, 12, 1)).rooms_revenue)
