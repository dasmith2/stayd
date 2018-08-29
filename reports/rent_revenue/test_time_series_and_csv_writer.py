from datetime import date

from util.tests import TestCase
from djmoney.money import Money

from rentals.models import Owner
from rentals.tests import get_test_owner, get_test_lease
from reports.rent_revenue.time_series import DAY, get_points
from reports.rent_revenue.csv_writer import write_csv
from reservations.models import (
    ReservationLineItem, KNOWN_LINE_ITEM_NAMES, Reservation)
from reservations.tests import get_test_reservation


def setup():
  """
  Date, Long Beach rent / day, New York rent / day
  3/2   0                      36
  3/3   12                     36
  3/4   24                     36
  """
  rent = KNOWN_LINE_ITEM_NAMES.RENT
  long_beach_owner = get_test_owner(True, name='The Queen of France')
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
  # averaged out over the year. So it's, like, monthly rent * 12 / 365 per day.
  # So it's a bit tricky picking test numbers that work out nice! If monthly
  # rent is 365, that means daily rent is 12.
  get_test_lease(
      True, rental=long_beach.rental, start_date=date(2018, 3, 3),
      rent=Money(365, 'USD'))  # a.k.a. daily rent is 12.
  get_test_lease(
      True, rental=long_beach.rental, start_date=date(2018, 3, 4),
      rent=Money(365 * 2, 'USD'))  # a.k.a. daily rent is 24.

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
  get_test_lease(
      True, rental=new_york.rental, start_date=date(2017, 1, 1),
      rent=Money(365 * 3, 'USD'))  # a.k.a. daily rent is 36.


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
        'Empire State Building total_charges', 'Empire State Building net']
    self.assertEqual(row_0, writer.rows[0])
    row_1 = ['2018-03-02', 0, -150.0, 0, -50.0, 0, -100.0]
    self.assertEqual(row_1, writer.rows[1])
    row_2 = ['2018-03-03', 50.0, -100.0, 0, -50.0, 50.0, -50.0]
    self.assertEqual(row_2, writer.rows[2])
    row_3 = ['2018-03-04', 100.0, -50.0, 50.0, 0, 50.0, -50.0]
    self.assertEqual(row_3, writer.rows[3])


class TimeSeriesTests(TestCase):
  def test_get_points(self):
    """
    Date, Long Beach rent / day, New York rent / day
    3/2   0                      36
    3/3   12                     36
    3/4   24                     36
    """
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
    self.assertEqual(Money(36, 'USD'), points_in_total[0].rent)
    # 1
    self.assertEqual(
        Money(50.0, 'USD'), points_in_total[1].total_charges)
    self.assertEqual(date(2018, 3, 3), points_in_total[1].from_date)
    self.assertEqual(1, points_in_total[1].occupied_days)
    self.assertEqual(Money(12 + 36, 'USD'), points_in_total[1].rent)
    # 2
    self.assertEqual(
        Money(100.0, 'USD'), points_in_total[2].total_charges)
    self.assertEqual(date(2018, 3, 4), points_in_total[2].from_date)
    self.assertEqual(2, points_in_total[2].occupied_days)
    self.assertEqual(Money(24 + 36, 'USD'), points_in_total[2].rent)

    city_points = get_points(
        date(2018, 3, 2), date(2018, 3, 5), DAY, city='Long Beach')
    self.assertEqual(1, city_points[0].max_occupancy)
    self.assertEqual(Money(0, 'USD'), city_points[0].rent)
    self.assertEqual(Money(12, 'USD'), city_points[1].rent)
    self.assertEqual(Money(0.0, 'USD'), city_points[1].total_charges)
    self.assertEqual(Money(50.0, 'USD'), city_points[2].total_charges)

    long_beach_owner = Owner.objects.get(name='The Queen of France')
    owner_points = get_points(
        date(2018, 3, 2), date(2018, 3, 5), DAY, owner_id=long_beach_owner.pk)
    self.assertEqual(1, owner_points[0].max_occupancy)
    self.assertEqual(Money(0, 'USD'), city_points[0].rent)
    self.assertEqual(Money(12, 'USD'), city_points[1].rent)
    self.assertEqual(Money(0.0, 'USD'), owner_points[1].total_charges)
    self.assertEqual(Money(50.0, 'USD'), owner_points[2].total_charges)


class FakeWriter(object):
  def __init__(self):
    self.rows = []

  def writerow(self, row):
    self.rows.append(row)
