from datetime import date
from decimal import Decimal

from djmoney.money import Money

from rentals.tests import get_test_owner, get_test_rental
from reservations.models import CONFIRMED, CANCELED
from reservations.tests import get_test_reservation, get_test_payment
from stats.models.computer import compute_stats
from stats.models.getter import StatsGetter
from stats.models.stale import Stale, save_point_to_stats
from stats.models.stats import Stats, MONTH, WEEK, DAY, TOTAL
from util.tests import TestCase
from util.timezone import str_to_tz_dt


class GetterTests(TestCase):
  def test_get_mid_month_total(self):
    reservation1 = get_test_reservation(
        check_in=str_to_tz_dt('2018-07-27 16:00'),  # So 5 days in July
        # 31 days in August
        check_out=str_to_tz_dt('2018-09-06 11:00'),  # and 5 in Sept
        room_line_item=Money(4100.0, 'USD'))  # So $100 a day.
    get_test_payment(reservation=reservation1, amount=Money(4100.0, 'USD'))
    Stale.objects.fix()

    # Querying 2 days in July, all of August, and 2 days in September
    stats = StatsGetter().get_stats(
        date(2018, 7, 30), date(2018, 9, 3), TOTAL,
        owner_id=reservation1.rental.building.owner.pk)
    stats_dict = stats.to_dict()
    self.assertEqual(3500, stats_dict['rooms_revenue'])
    self.assertEqual(
        round(float(Decimal(35 / 41)), 2),
        round(stats_dict['reservation_count'], 2))
    self.assertEqual(41, round(stats_dict['average_stay']))
    # Querying 2 days in July, 2 days in August
    stats = StatsGetter().get_stats(
        date(2018, 7, 30), date(2018, 8, 3), TOTAL,
        owner_id=reservation1.rental.building.owner.pk)
    self.assertEqual(400, stats.rooms_revenue)
    # Querying by week. Sundays are on 7/29, 8/5, 8/12, 8/19, 8/26, 9/2
    stats = StatsGetter().get_stats(
        date(2018, 7, 29), date(2018, 9, 9), WEEK,
        owner_id=reservation1.rental.building.owner.pk)
    self.assertEqual(6, len(stats))
    self.assertEqual(date(2018, 7, 29), stats[0].from_date)
    self.assertEqual(WEEK, stats[0].interval)
    self.assertEqual(700, stats[0].rooms_revenue)
    self.assertEqual(400, stats[5].rooms_revenue)

  def test_get_occupancy_stuff(self):
    the_queen = get_test_owner(username='TheQueen')
    rental = get_test_rental(
        owner=the_queen, reports_start_date=date(2018, 5, 2))
    get_test_reservation(
        rental=rental, check_in=str_to_tz_dt('2018-05-03 16:00'),
        check_out=str_to_tz_dt('2018-05-04 11:00'), status=CONFIRMED)
    get_test_reservation(
        rental=rental, check_in=str_to_tz_dt('2018-05-03 16:00'),
        check_out=str_to_tz_dt('2018-05-04 11:00'),
        canceled_at=str_to_tz_dt('2018-10-16 12:00'), status=CANCELED)
    self.assertEqual(rental.reports_start_date, date(2018, 5, 2))
    get_test_rental(owner=the_queen, reports_start_date=date(2018, 5, 3))
    statses = compute_stats(
        date(2018, 5, 1), date(2018, 5, 4), DAY, owner_id=the_queen.pk)
    self.assertEqual(0, statses[0].nights_available)
    self.assertEqual(1, statses[1].nights_available)
    self.assertEqual(2, statses[2].nights_available)
    # Don't include the canceled reservation in these.
    self.assertEqual(1, statses[2].nights_occupied)
    self.assertEqual(1, statses[2].reservation_count)

  def test_get_stats(self):
    queen_of_spain = get_test_owner(username='TheQueenofSpain')
    reservation1 = get_test_reservation(
        owner=queen_of_spain,
        check_in=str_to_tz_dt('2018-06-02 16:00'),
        check_out=str_to_tz_dt('2018-06-03 11:00'),
        nickname='Burlington house',
        city='Burlington', status=CONFIRMED,
        room_line_item=Money(100.0, 'USD'))
    get_test_payment(reservation=reservation1, amount=Money(100.0, 'USD'))

    reservation2 = get_test_reservation(
        owner=queen_of_spain,
        check_in=str_to_tz_dt('2018-08-29 16:00'),  # So 3 days in August
        check_out=str_to_tz_dt('2018-09-03 11:00'),  # and 2 in September
        nickname='Lebanon house',
        city='Lebanon', status=CONFIRMED,
        room_line_item=Money(500.0, 'USD'))
    get_test_payment(reservation=reservation2, amount=Money(500.0, 'USD'))

    # This should run hourly. We COULD just fix stats as soon as the
    # reservation syncs, but I'm worried that will DOS the worker thread
    # because sometimes guesty will send bursts of webhooks.
    Stale.objects.fix()

    # Day, Rental.
    statses = StatsGetter().get_stats(
        date(2018, 6, 1), date(2018, 6, 4), DAY,
        rental_id=reservation1.rental.pk)
    self.assertEqual(3, len(statses))
    self.assertEqual(0, statses[0].rooms_revenue)
    self.assertEqual(100, statses[1].rooms_revenue)
    self.assertEqual(0, statses[2].rooms_revenue)

    # Month, Owner.
    statses = StatsGetter().get_stats(
        date(2018, 5, 1), date(2018, 11, 1), MONTH, owner_id=queen_of_spain.pk)
    self.assertEqual(6, len(statses))
    self.assertEqual(0, statses[0].rooms_revenue)  # 5
    self.assertEqual(100, statses[1].rooms_revenue)  # 6
    self.assertEqual(0, statses[2].rooms_revenue)  # 7
    self.assertEqual(300, statses[3].rooms_revenue)  # 8
    self.assertEqual(200, statses[4].rooms_revenue)  # 9
    self.assertEqual(0, statses[5].rooms_revenue)  # 10
    self.assertEqual('Oct 2018', statses[5].get_label())

    # Total, Building.
    stats = StatsGetter().get_stats(
        date(2018, 5, 1), date(2018, 11, 1), TOTAL,
        building_id=reservation1.rental.building.pk, owner_id=None)
    self.assertEqual(100, stats.rooms_revenue)

  def test_save_point_to_stats_to_dict(self):
    """ Just make sure the pipeline from a point to the database to the loaded
    stats to the dict is intact. """
    point = Stats(
        rooms_revenue=Decimal(2.3),
        cleaning_income=Decimal(3.4),
        upsell_income=Decimal(0.1),
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
        point, get_test_owner(), None, None)
    stats.refresh_from_db()
    dct = stats.to_dict()
    self.assertEqual(dct['rooms_revenue'], 2.3)
    self.assertEqual(dct['cleaning_income'], 3.4)
    self.assertEqual(dct['upsell_income'], 0.1)
    self.assertEqual(dct['taxes'], 6.7)
    self.assertEqual(dct['revenue'], 12.5)
    self.assertEqual(dct['cleaning_fees'], 4.5)
    self.assertEqual(dct['channel_fees'], 5.6)
    self.assertEqual(dct['rent'], 7.8)
    self.assertEqual(dct['nights_available'], 3)
    self.assertEqual(dct['nights_occupied'], 2)
    self.assertEqual(dct['from_date'], '2018-05-01')
    self.assertEqual(dct['interval'], MONTH)
    self.assertEqual(dct['reservation_count'], 1)
