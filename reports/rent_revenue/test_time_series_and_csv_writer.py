from datetime import date

from util.tests import TestCase
from djmoney.money import Money

from rentals.models import RENT
from rentals.tests import get_test_owner, get_test_monthly_expense
from reports.rent_revenue.time_series import DAY
from reports.rent_revenue.csv_writer import write_csv
from reservations.models import (
    ReservationLineItem, KNOWN_LINE_ITEM_NAMES, Reservation)
from reservations.tests import get_test_reservation


def setup():
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
  # averaged out over the year. So it's, like, monthly rent * 12 / 365 per day.
  # So it's a bit tricky picking test numbers that work out nice! If monthly
  # rent is 365, that means daily rent is 12.

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


class CSVTests(TestCase):
  def test_write_csv(self):
    setup()
    writer = FakeWriter()
    from_date, to_date, interval = date(2018, 3, 2), date(2018, 3, 5), DAY
    all_units_aggregate = True
    cities = ['Long Beach']
    new_york = Reservation.objects.get(channel_reservation_id='new_york_res')
    rental_ids = [new_york.rental.pk]
    seriesies = ['total_income', 'net']
    write_csv(
        writer, from_date, to_date, interval, all_units_aggregate, cities,
        rental_ids, seriesies)

    self.assertEqual(4, len(writer.rows))
    row_0 = [
        'Date', 'All units total_income', 'All units net',
        'Long Beach total_income', 'Long Beach net',
        'Empire State Building total_income', 'Empire State Building net']
    self.assertEqual(row_0, writer.rows[0])
    row_1 = ['2018-03-02', 0, -36.0, 0, 0, 0, -36.0]
    self.assertEqual(row_1, writer.rows[1])
    row_2 = ['2018-03-03', 50.0, 2.0, 0, -12.0, 50.0, 14.0]
    self.assertEqual(row_2, writer.rows[2])
    row_3 = ['2018-03-04', 100.0, 40.0, 50.0, 26.0, 50.0, 14.0]
    self.assertEqual(row_3, writer.rows[3])


class FakeWriter(object):
  def __init__(self):
    self.rows = []

  def writerow(self, row):
    self.rows.append(row)
