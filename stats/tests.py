from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from djmoney.money import Money

from rentals.models import RENT
from rentals.tests import (
    get_test_owner, get_test_monthly_expense, get_test_rental)
from reservations.models import (
    ReservationLineItem, KNOWN_LINE_ITEM_NAMES, Reservation)
from reservations.tests import get_test_reservation
from stats.models.computer import compute_stats, reservation_res_stats
from stats.models.getter import StatsGetter
from stats.models.stats import Stats, TOTAL, MONTH, DAY
from stats.models.stale import Stale, OldStale, save_point_to_stats
from util.signals import post_sync
from util.tests import TestCase
from util.timezone import str_to_tz_dt


class GetterTests(TestCase):
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
    stats = StatsGetter().get_stats(
        date(2018, 7, 30), date(2018, 9, 3), TOTAL,
        owner_id=reservation1.rental.building.owner.pk)
    stats_dict = stats.to_dict()
    self.assertEqual(3500, stats_dict['room_income'])
    self.assertEqual(
        round(float(Decimal(35 / 41)), 2),
        round(stats_dict['reservation_count'], 2))
    self.assertEqual(41, round(stats_dict['average_stay']))
    # Querying 2 days in July, 2 days in August
    stats = StatsGetter().get_stats(
        date(2018, 7, 30), date(2018, 8, 3), TOTAL,
        owner_id=reservation1.rental.building.owner.pk)
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

    # Month, Owner. This is appropriate for the cache.
    statses = StatsGetter().get_stats(
        date(2018, 5, 1), date(2018, 11, 1), MONTH,
        building_id=None, owner_id=queen_of_spain.pk)
    self.assertEqual(6, len(statses))
    self.assertEqual(0, statses[0].room_income)  # 5
    self.assertEqual(100, statses[1].room_income)  # 6
    self.assertEqual(0, statses[2].room_income)  # 7
    self.assertEqual(300, statses[3].room_income)  # 8
    self.assertEqual(200, statses[4].room_income)  # 9
    self.assertEqual(0, statses[5].room_income)  # 10
    self.assertEqual('Oct 2018', statses[5].get_label())

    # Total, Rental. Appropriate for the cache.
    stats = StatsGetter().get_stats(
        date(2018, 5, 1), date(2018, 11, 1), TOTAL,
        building_id=reservation1.rental.building.pk, owner_id=None)
    self.assertEqual(100, stats.room_income)

  def test_save_point_to_stats_to_dict(self):
    """ Just make sure the pipeline from a point to the database to the loaded
    stats to the dict is intact. """
    point = Stats(
        room_income=Decimal(2.3),
        cleaning_income=Decimal(3.4),
        cleaning_fees=Decimal(4.5),
        channel_fees=Decimal(5.6),
        taxes=Decimal(6.7),
        rent=Decimal(7.8),
        nights_available=3,
        nights_occupied=2,
        from_date=date(2018, 5, 1),
        interval=MONTH,
        reservation_count=Decimal(1))
    stats = save_point_to_stats(
        point, get_test_owner(True), None, None)
    stats.refresh_from_db()
    dct = stats.to_dict()
    self.assertEqual(dct['room_income'], 2.3)
    self.assertEqual(dct['cleaning_income'], 3.4)
    self.assertEqual(dct['taxes'], 6.7)
    self.assertEqual(dct['total_income'], 12.4)
    self.assertEqual(dct['cleaning_fees'], 4.5)
    self.assertEqual(dct['channel_fees'], 5.6)
    self.assertEqual(dct['rent'], 7.8)
    self.assertEqual(dct['nights_available'], 3)
    self.assertEqual(dct['nights_occupied'], 2)
    self.assertEqual(dct['from_date'], '2018-05-01')
    self.assertEqual(dct['interval'], MONTH)
    self.assertEqual(dct['reservation_count'], 1)


class StaleTests(TestCase):
  def test_mark_stale_due_to_reservation(self):
    self.assertEqual(0, Stale.objects.count())
    reservation = get_test_reservation(True)
    Stale.objects.mark_stale_due_to_reservation(reservation)
    # One for the owner and one for the rental.
    self.assertEqual(2, Stale.objects.count())
    Stale.objects.mark_stale_due_to_reservation(reservation)
    self.assertEqual(2, Stale.objects.count())

  def test_mark_all_stats_stale(self):
    res = get_test_reservation(
        True,
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

    Stale.objects.mark_all_stats_stale()

    self.assertEqual(3, Stale.objects.count())

    Stale.objects.fix()

    self.assertEqual(0, Stale.objects.count())
    self.assertEqual(3, OldStale.objects.count())

  def test_mark_stale_due_to_monthly_expense(self):
    rental = get_test_rental(True)
    self.assertEqual(0, Stats.objects.count())
    self.assertEqual(Decimal(0), StatsGetter().get_stats(
        date(2018, 5, 1), date(2018, 6, 1), TOTAL,
        building_id=rental.building.pk).rent)

    get_test_monthly_expense(
        True, rental=rental, start_date=date(2018, 5, 1),
        monthly_amount=Money(100, 'USD'), kind=RENT)
    Stale.objects.fix()

    self.assertTrue(Stats.objects.count() > 0)
    # Remember that monthly expenses are smoothed out for the whole year. This
    # is 31 days in May times the daily amount of $100 rent when you smooth it
    # out over all the days in the year, rounded to 2 places.
    expected_rent = Decimal(31 * 12 * 100 / 365)
    got_rent = StatsGetter().get_stats(
        date(2018, 5, 1), date(2018, 6, 1), TOTAL,
        building_id=rental.building.pk).rent
    self.assertEqual(round(expected_rent, 2), round(got_rent, 2))


class ComputerTests(TestCase):
  def setup(self):
    """
    Rent / leases situation:
    Date, total rent / day, Long Beach rent / day, New York rent / day
    3/2   36                0                      36
    3/3   48                12                     36
    3/4   60                24                     36

    Profit situation:
    Date, total income, Long Beach income, New York income
    3/2   0             0                  0
    3/3   50            0                  50
    3/4   100           50                 50
    3/5   50            50                 0
    """
    rent = KNOWN_LINE_ITEM_NAMES.RENT
    long_beach_owner = get_test_owner(True, username='TheQueenofFrance')
    long_beach = get_test_reservation(
        True, city='Long Beach',
        owner=long_beach_owner,
        check_in='2018-03-04 16:00',
        check_out='2018-03-06 11:00',
        channel_reservation_id='long_beach_res')
    ReservationLineItem.objects.create(
        name=rent,
        value=Money(100.0, 'USD'),
        reservation=long_beach)
    # For the purposes of reporting, we pretend to pay the same rent daily
    # averaged out over the year. So it's, like, monthly rent * 12 / 365 per
    # day.  So it's a bit tricky picking test numbers that work out nice! If
    # monthly rent is 365, that means daily rent is 12.

    # daily rent is 12.
    get_test_monthly_expense(
        True, rental=long_beach.rental, start_date=date(2018, 3, 3),
        monthly_amount=Money(365, 'USD'), kind=RENT)
    # daily rent is 24.
    get_test_monthly_expense(
        True, rental=long_beach.rental, start_date=date(2018, 3, 4),
        monthly_amount=Money(365 * 2, 'USD'), kind=RENT)

    new_york = get_test_reservation(
        True, city='New York',
        check_in='2018-03-03 16:00',
        check_out='2018-03-05 11:00',
        channel_reservation_id='new_york_res',
        nickname='Empire State Building')
    ReservationLineItem.objects.create(
        name=rent,
        value=Money(100.0, 'USD'),
        reservation=new_york)
    # daily rent is 36.
    get_test_monthly_expense(
        True, rental=new_york.rental, start_date=date(2017, 1, 1),
        monthly_amount=Money(365 * 3, 'USD'), kind=RENT)

  def test_compute_stats(self):
    """
    Date, Long Beach rent / day, New York rent / day
    3/2   0                      36
    3/3   12                     36
    3/4   24                     36
    """
    self.setup()

    points_in_total = compute_stats(date(2018, 3, 2), date(2018, 3, 5), DAY)
    self.assertEqual(3, len(points_in_total))
    # 0
    self.assertEqual(date(2018, 3, 2), points_in_total[0].from_date)
    self.assertEqual(DAY, points_in_total[0].interval)
    self.assertEqual(2, points_in_total[0].nights_available)
    self.assertEqual(0, points_in_total[0].nights_occupied)
    self.assertEqual(
        Decimal(0.0), points_in_total[0].total_income())
    self.assertEqual(Decimal(36), points_in_total[0].rent)
    # 1
    self.assertEqual(
        Decimal(50.0), points_in_total[1].total_income())
    self.assertEqual(date(2018, 3, 3), points_in_total[1].from_date)
    self.assertEqual(1, points_in_total[1].nights_occupied)
    self.assertEqual(Decimal(12 + 36), points_in_total[1].rent)
    # 2
    self.assertEqual(
        Decimal(100.0), points_in_total[2].total_income())
    self.assertEqual(date(2018, 3, 4), points_in_total[2].from_date)
    self.assertEqual(2, points_in_total[2].nights_occupied)
    self.assertEqual(Decimal(24 + 36), points_in_total[2].rent)

    city_points = compute_stats(
        date(2018, 3, 2), date(2018, 3, 5), DAY, city='Long Beach')
    self.assertEqual(1, city_points[0].nights_available)
    self.assertEqual(Decimal(0), city_points[0].rent)
    self.assertEqual(Decimal(12), city_points[1].rent)
    self.assertEqual(Decimal(0.0), city_points[1].total_income())
    self.assertEqual(Decimal(50.0), city_points[2].total_income())

    long_beach_owner = User.objects.get(username='TheQueenofFrance')
    owner_points = compute_stats(
        date(2018, 3, 2), date(2018, 3, 5), DAY, owner_id=long_beach_owner.pk)
    self.assertEqual(1, owner_points[0].nights_available)
    self.assertEqual(Decimal(0), city_points[0].rent)
    self.assertEqual(Decimal(12), city_points[1].rent)
    self.assertEqual(Decimal(0.0), owner_points[1].total_income())
    self.assertEqual(Decimal(50.0), owner_points[2].total_income())

  def test_reservation_res_stats(self):
    reservation = get_test_reservation(True)
    names = KNOWN_LINE_ITEM_NAMES
    ReservationLineItem.objects.create(
        name=names.RENT,
        value=Money(100.0, 'USD'),
        reservation=reservation)
    ReservationLineItem.objects.create(
        name=names.HOST_CHANNEL_FEE,
        value=Money(-10.0, 'USD'),
        reservation=reservation)
    ReservationLineItem.objects.create(
        name=names.CLEANING_FEE,
        value=Money(50.0, 'USD'),
        reservation=reservation)
    charges_and_fees = reservation_res_stats(reservation)
    self.assertEqual(charges_and_fees.total_income(), Decimal('150'))
    self.assertEqual(charges_and_fees.cleaning_fees, Decimal('50'))
    self.assertEqual(charges_and_fees.channel_fees, Decimal(10))
