from datetime import date
from decimal import Decimal

from djmoney.money import Money

from rentals.tests import get_test_owner
from reports.rent_revenue.time_series import Point
from reservations.models import (
    ReservationLineItem, KNOWN_LINE_ITEM_NAMES, Reservation)
from reservations.tests import get_test_reservation
from stats.models import Stats, Stale, OldStale, TOTAL, MONTH, DAY
from util.signals import post_sync
from util.tests import TestCase
from util.timezone import str_to_tz_dt


class StatsTests(TestCase):
  """ There are grittier math tests in test_time_series_and_csv_writer. This is
  mainly to make sure everything is wired up right. """
  def test_get_mid_month_total(self):
    reservation1 = get_test_reservation(
        True,
        check_in=str_to_tz_dt('2018-07-27 16:00'),  # So 5 days in July
        # 31 days in August
        check_out=str_to_tz_dt('2018-09-06 11:00'))  # and 5 in Sept
    ReservationLineItem.objects.create(
        name=KNOWN_LINE_ITEM_NAMES.RENT,
        value=Money(4100.0, 'USD'),  # So $100 a day.
        reservation=reservation1)
    post_sync.send(sender=Reservation, instance=reservation1)
    Stale.objects.fix()

    # Querying 2 days in July, all of August, and 2 days in September
    stats = Stats.objects.get_stats(
        date(2018, 7, 30), date(2018, 9, 3), TOTAL,
        owner_id=reservation1.rental.owner.pk)
    self.assertEqual(3500, stats.to_dict()['room_income'])
    # Querying 2 days in July, 2 days in August
    stats = Stats.objects.get_stats(
        date(2018, 7, 30), date(2018, 8, 3), TOTAL,
        owner_id=reservation1.rental.owner.pk)
    self.assertEqual(400, stats.room_income)

  def test_get_stats(self):
    rent = KNOWN_LINE_ITEM_NAMES.RENT
    queen_of_spain = get_test_owner(True, username='TheQueenofSpain')
    reservation1 = get_test_reservation(
        True,
        owner=queen_of_spain,
        check_in=str_to_tz_dt('2018-06-01 16:00'),
        check_out=str_to_tz_dt('2018-06-02 11:00'),
        nickname='Burlington house',
        city='Burlington')
    ReservationLineItem.objects.create(
        name=rent,
        value=Money(100.0, 'USD'),
        reservation=reservation1)
    post_sync.send(sender=Reservation, instance=reservation1)

    reservation2 = get_test_reservation(
        True,
        owner=queen_of_spain,
        check_in=str_to_tz_dt('2018-08-29 16:00'),  # So 3 days in August
        check_out=str_to_tz_dt('2018-09-03 11:00'),  # and 2 in September
        nickname='Lebanon house',
        city='Lebanon')
    ReservationLineItem.objects.create(
        name=rent,
        value=Money(500.0, 'USD'),
        reservation=reservation2)
    post_sync.send(sender=Reservation, instance=reservation2)

    # This should run hourly. We COULD just fix stats as soon as the
    # reservation syncs, but I'm worried that will DOS the worker thread
    # because sometimes guesty will send bursts of webhooks.
    Stale.objects.fix()

    # Day, City
    statses = Stats.objects.get_stats(
        date(2018, 8, 29), date(2018, 9, 3), DAY, city='Lebanon',
        rental_id=None, owner_id=queen_of_spain.pk)
    self.assertEqual(5, len(statses))
    self.assertEqual(100, statses[0].room_income)
    self.assertEqual(100, statses[4].room_income)

    # Month, Owner
    statses = Stats.objects.get_stats(
        date(2018, 5, 1), date(2018, 11, 1), MONTH, city=None,
        rental_id=None, owner_id=queen_of_spain.pk)
    self.assertEqual(6, len(statses))
    self.assertEqual(0, statses[0].room_income)  # 5
    self.assertEqual(100, statses[1].room_income)  # 6
    self.assertEqual(0, statses[2].room_income)  # 7
    self.assertEqual(300, statses[3].room_income)  # 8
    self.assertEqual(200, statses[4].room_income)  # 9
    self.assertEqual(0, statses[5].room_income)  # 10
    self.assertEqual('Oct 2018', statses[5].get_label())

    # Total, Rental
    stats = Stats.objects.get_stats(
        date(2018, 5, 1), date(2018, 11, 1), TOTAL, city=None,
        rental_id=reservation1.rental.pk, owner_id=None)
    self.assertEqual(100, stats.room_income)

  def test_save_point_to_stats_to_dict(self):
    """ Just make sure the pipeline from a point to the database to the loaded
    stats to the dict is intact. """
    point = Point(
        room_income=Money(2.3, 'USD'),
        cleaning_income=Money(3.4, 'USD'),
        total_income=Money(5.7, 'USD'),
        cleaning_fees=Money(4.5, 'USD'),
        channel_fees=Money(5.6, 'USD'),
        taxes=Money(6.7, 'USD'),
        rent=Money(7.8, 'USD'),
        max_occupancy=3,
        occupied_days=2,
        from_date=date(2018, 5, 1),
        interval=MONTH)
    stats = Stats.objects._save_point_to_stats(
        point, get_test_owner(True), None, None)
    stats.refresh_from_db()
    dct = stats.to_dict()
    self.assertEqual(dct['room_income'], Decimal('2.3'))
    self.assertEqual(dct['cleaning_income'], Decimal('3.4'))
    self.assertEqual(dct['total_income'], Decimal('5.7'))
    self.assertEqual(dct['cleaning_fees'], Decimal('4.5'))
    self.assertEqual(dct['channel_fees'], Decimal('5.6'))
    self.assertEqual(dct['taxes'], Decimal('6.7'))
    self.assertEqual(dct['rent'], Decimal('7.8'))
    self.assertEqual(dct['max_occupancy'], 3)
    self.assertEqual(dct['occupied_days'], 2)
    self.assertEqual(dct['from_date'], '2018-05-01')
    self.assertEqual(dct['interval'], MONTH)


class StaleTests(TestCase):
  def test_mark_stale_due_to_reservation(self):
    self.assertEqual(0, Stale.objects.count())
    reservation = get_test_reservation(True)
    Stale.objects.mark_stale_due_to_reservation(reservation)
    # One for the owner, one for the city, one for the rental.
    self.assertEqual(3, Stale.objects.count())
    Stale.objects.mark_stale_due_to_reservation(reservation)
    self.assertEqual(3, Stale.objects.count())

  def test_mark_all_stats_stale(self):
    res = get_test_reservation(
        True,
        check_in=str_to_tz_dt('2018-06-01 16:00'),
        check_out=str_to_tz_dt('2018-06-02 11:00'))
    # This one shouldn't cause an extra stale because it includes the above
    # reservation.
    Stats.objects.create(
        start_date=res.check_in.date(), interval=MONTH,
        owner=res.rental.owner)
    # But this one should cause an extra stale.
    Stats.objects.create(
        start_date=date(2018, 5, 1), interval=MONTH,
        owner=res.rental.owner)

    Stale.objects.mark_all_stats_stale()

    self.assertEqual(4, Stale.objects.count())

    Stale.objects.fix()

    self.assertEqual(0, Stale.objects.count())
    self.assertEqual(4, OldStale.objects.count())
