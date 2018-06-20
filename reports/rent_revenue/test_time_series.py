from datetime import date

from django.test import TestCase
from djmoney.money import Money

from reports.rent_revenue.time_series import DAY, get_points
from reservations.models import ReservationLineItem, KNOWN_LINE_ITEM_NAMES
from reservations.tests import get_test_reservation


class TimeSeriesTests(TestCase):
  def test_get_points(self):
    rent = KNOWN_LINE_ITEM_NAMES.RENT
    long_beach = get_test_reservation(
        True, city='Long Beach', check_in='2018-03-04 16:00',
        check_out='2018-03-06 11:00')
    ReservationLineItem.objects.create(
        name=rent,
        value=Money(100.0, 'USD'),
        reservation=long_beach)
    new_york = get_test_reservation(
        True, city='New York', check_in='2018-03-03 16:00',
        check_out='2018-03-05 11:00')
    ReservationLineItem.objects.create(
        name=rent,
        value=Money(100.0, 'USD'),
        reservation=new_york)

    points_in_total = get_points(date(2018, 3, 2), date(2018, 3, 5), DAY)
    self.assertEqual(3, len(points_in_total))
    self.assertEqual(
        Money(0.0, 'USD'), points_in_total[0].total_charges)
    # 0
    self.assertEqual(date(2018, 3, 2), points_in_total[0].from_date)
    self.assertEqual(DAY, points_in_total[0].interval)
    self.assertEqual(2, points_in_total[0].max_occupancy)
    self.assertEqual(0, points_in_total[0].occupied_days)
    # 1
    self.assertEqual(
        Money(50.0, 'USD'), points_in_total[1].total_charges)
    self.assertEqual(date(2018, 3, 3), points_in_total[1].from_date)
    self.assertEqual(1, points_in_total[1].occupied_days)
    # 2
    self.assertEqual(
        Money(100.0, 'USD'), points_in_total[2].total_charges)
    self.assertEqual(date(2018, 3, 4), points_in_total[2].from_date)
    self.assertEqual(2, points_in_total[2].occupied_days)

    city_points = get_points(
        date(2018, 3, 2), date(2018, 3, 5), DAY, city='Long Beach')
    self.assertEqual(1, city_points[0].max_occupancy)
    self.assertEqual(Money(0.0, 'USD'), city_points[1].total_charges)
    self.assertEqual(Money(50.0, 'USD'), city_points[2].total_charges)
