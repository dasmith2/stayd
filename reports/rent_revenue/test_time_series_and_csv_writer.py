from datetime import date

from util.tests import TestCase
from djmoney.money import Money

from rentals.models import Owner
from rentals.tests import get_test_owner
from reports.rent_revenue.time_series import DAY, get_points
from reports.rent_revenue.csv_writer import write_csv
from reservations.models import (
    ReservationLineItem, KNOWN_LINE_ITEM_NAMES, Reservation)
from reservations.tests import get_test_reservation


def setup():
  rent = KNOWN_LINE_ITEM_NAMES.RENT
  long_beach_owner = get_test_owner(True, name='The Queen of France')
  long_beach = get_test_reservation(
      True, city='Long Beach',
      owner=long_beach_owner,
      check_in='2018-03-04 16:00',
      check_out='2018-03-06 11:00',
      market_rent=Money(1550, 'USD'),
      channel_reservation_id='long_beach_res')
  ReservationLineItem.objects.create(
      name=rent,
      value=Money(100.0, 'USD'),
      reservation=long_beach)
  new_york = get_test_reservation(
      True, city='New York',
      check_in='2018-03-03 16:00',
      check_out='2018-03-05 11:00',
      market_rent=Money(3100, 'USD'),
      channel_reservation_id='new_york_res',
      nickname='Buckingham')
  ReservationLineItem.objects.create(
      name=rent,
      value=Money(100.0, 'USD'),
      reservation=new_york)


class CSVTests(TestCase):
  def test_write_csv(self):
    setup()
    writer = FakeWriter()
    from_date, to_date, interval = date(2018, 3, 2), date(2018, 3, 5), DAY
    all_units_aggregate = True
    cities = ['Long Beach']
    new_york = Reservation.objects.get(channel_reservation_id='new_york_res')
    rental_ids = [new_york.rental.pk]
    seriesies = ['total_charges', 'net']
    write_csv(
        writer, from_date, to_date, interval, all_units_aggregate, cities,
        rental_ids, seriesies)

    self.assertEqual(4, len(writer.rows))
    row_0 = [
        'Date', 'All units total_charges', 'All units net',
        'Long Beach total_charges', 'Long Beach net',
        'Buckingham total_charges', 'Buckingham net']
    self.assertEqual(row_0, writer.rows[0])
    row_1 = ['2018-03-02', 0, -150.0, 0, -50.0, 0, -100.0]
    self.assertEqual(row_1, writer.rows[1])
    row_2 = ['2018-03-03', 50.0, -100.0, 0, -50.0, 50.0, -50.0]
    self.assertEqual(row_2, writer.rows[2])
    row_3 = ['2018-03-04', 100.0, -50.0, 50.0, 0, 50.0, -50.0]
    self.assertEqual(row_3, writer.rows[3])


class TimeSeriesTests(TestCase):
  def test_get_points(self):
    setup()

    points_in_total = get_points(date(2018, 3, 2), date(2018, 3, 5), DAY)
    self.assertEqual(3, len(points_in_total))
    # 0
    self.assertEqual(date(2018, 3, 2), points_in_total[0].from_date)
    self.assertEqual(DAY, points_in_total[0].interval)
    self.assertEqual(2, points_in_total[0].max_occupancy)
    self.assertEqual(0, points_in_total[0].occupied_days)
    self.assertEqual(
        Money(0.0, 'USD'), points_in_total[0].total_charges)
    self.assertEqual(Money(150, 'USD'), points_in_total[0].rent)
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
    self.assertEqual(Money(50, 'USD'), city_points[0].rent)
    self.assertEqual(Money(0.0, 'USD'), city_points[1].total_charges)
    self.assertEqual(Money(50.0, 'USD'), city_points[2].total_charges)

    long_beach_owner = Owner.objects.get(name='The Queen of France')
    owner_points = get_points(
        date(2018, 3, 2), date(2018, 3, 5), DAY, owner_id=long_beach_owner.pk)
    self.assertEqual(1, owner_points[0].max_occupancy)
    self.assertEqual(Money(50, 'USD'), owner_points[0].rent)
    self.assertEqual(Money(0.0, 'USD'), owner_points[1].total_charges)
    self.assertEqual(Money(50.0, 'USD'), owner_points[2].total_charges)


class FakeWriter(object):
  def __init__(self):
    self.rows = []

  def writerow(self, row):
    self.rows.append(row)
