from datetime import date
from decimal import Decimal

from djmoney.money import Money

from expenses.models import Expense
from expenses.tests import get_test_expense
from nps.tests.test_rating import get_test_rating
from rentals.models import RENT
from rentals.tests import (
    get_test_building, get_test_rental, get_test_monthly_expense)
from reservations.models import Reservation
from reservations.tests import get_test_reservation
from stats.models.getter import StatsGetter
from stats.models.stale import Stale
from stats.models.stats import Stats, TOTAL, MONTH
from util.signals import post_sync
from util.tests import TestCase
from util.timezone import str_to_tz_dt


class StaleTests(TestCase):
  def test_post_save_rating(self):
    rental = get_test_rental()
    get_test_rating(
        check_in=str_to_tz_dt('2018-12-25 16:00'),
        check_out=str_to_tz_dt('2018-12-26 11:00'), rental=rental)
    Stale.objects.get(
        stats__from_date=date(2018, 12, 1), stats__interval=MONTH,
        stats__rental=rental)

  def test_post_save_rental(self):
    building = get_test_building()
    combo = get_test_rental(building=building)
    Stats.objects.create(
        from_date=date(2018, 12, 1), interval=MONTH, rental=combo)
    atom = get_test_rental(building=building)
    combo.is_combo_of.set([atom])
    self.assertFalse(Stats.objects.filter(rental=combo).exists())
    Stale.objects.get(
        stats__from_date=date(2018, 12, 1), stats__interval=MONTH,
        stats__rental=atom)

  def test_mark_stale_due_to_expense(self):
    building = get_test_building()
    expense = get_test_expense(building=building, month=date(2018, 5, 1))
    self.assertEqual(0, Stale.objects.count())

    for i in range(2):
      post_sync.send(sender=Expense, instance=expense)

    self.assertEqual(2, Stale.objects.count())
    Stale.objects.get(
        stats__building=building, stats__from_date=date(2018, 5, 1))
    Stale.objects.get(
        stats__owner=building.owner, stats__from_date=date(2018, 5, 1))

  def test_mark_stale_due_to_reservation(self):
    reservation = get_test_reservation(
        check_in=str_to_tz_dt('2018-05-31 00:00'),
        check_out=(str_to_tz_dt('2018-06-02 00:00')))
    self.assertEqual(0, Stale.objects.count())

    for i in range(2):
      post_sync.send(sender=Reservation, instance=reservation)

    self.assertEqual(6, Stale.objects.count())
    Stale.objects.get(
        stats__rental=reservation.rental, stats__from_date=date(2018, 5, 1))
    Stale.objects.get(
        stats__rental=reservation.rental, stats__from_date=date(2018, 6, 1))
    Stale.objects.get(
        stats__building=reservation.rental.building,
        stats__from_date=date(2018, 5, 1))
    Stale.objects.get(
        stats__building=reservation.rental.building,
        stats__from_date=date(2018, 6, 1))
    Stale.objects.get(
        stats__owner=reservation.rental.building.owner,
        stats__from_date=date(2018, 5, 1))
    Stale.objects.get(
        stats__owner=reservation.rental.building.owner,
        stats__from_date=date(2018, 6, 1))

  def test_mark_all_stale(self):
    res = get_test_reservation(
        check_in=str_to_tz_dt('2018-06-01 16:00'),
        check_out=str_to_tz_dt('2018-06-02 11:00'))
    # This one shouldn't cause an extra stale because it includes the above
    # reservation.
    Stats.objects.create(
        from_date=res.check_in.date(), interval=MONTH,
        owner=res.rental.building.owner)
    # But this one should cause an extra stale.
    Stats.objects.create(
        from_date=date(2018, 5, 1), interval=MONTH,
        owner=res.rental.building.owner)

    Stale.objects.mark_all_stale()

    self.assertEqual(2, Stale.objects.count())

    Stale.objects.fix()

    self.assertEqual(0, Stale.objects.count())

  def test_mark_stale_due_to_monthly_expense(self):
    rental = get_test_rental()
    self.assertEqual(0, Stats.objects.count())
    self.assertEqual(Decimal(0), StatsGetter().get_stats(
        date(2018, 5, 1), date(2018, 6, 1), TOTAL,
        building_id=rental.building.pk).rent)

    get_test_monthly_expense(
        rental=rental, start_date=date(2018, 5, 1),
        monthly_amount=Money(100, 'USD'), kind=RENT)
    Stale.objects.fix()

    self.assertTrue(Stats.objects.count() > 0)
    got_rent = StatsGetter().get_stats(
        date(2018, 5, 1), date(2018, 6, 1), TOTAL,
        building_id=rental.building.pk).rent
    self.assertEqual(Decimal('100'), round(got_rent, 2))
