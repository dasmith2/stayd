from datetime import date

from util.tests import TestCase

from reports.rent_revenue.csv_writer import write_csv, COMBINE, SEPARATE
from rentals.models import Rental
from reservations.models import Reservation
from stats.models.stats import DAY
from stats.models.stale import Stale


class CSVTests(TestCase):
  def test_write_csv(self):
    from stats.tests.test_computer import setup_computer_tests
    setup_computer_tests()
    for reservation in Reservation.objects.all():
      Stale.objects.mark_stale_due_to_reservation(reservation)
    Stale.objects.fix()

    empire_state_basement = Rental.objects.get(
        nickname='Empire State Basement')
    long_beach_dungeon = Rental.objects.get(
        nickname='Long Beach Castle Dungeon')

    from_date, to_date, interval = date(2018, 3, 2), date(2018, 3, 5), DAY
    rental_ids = [empire_state_basement.pk, long_beach_dungeon.pk]
    seriesies = ['revenue', 'rent']

    writer = FakeWriter()
    write_csv(
        writer, from_date, to_date, interval, SEPARATE,
        rental_ids, seriesies)

    self.assertEqual(4, len(writer.rows))
    row_0 = [
        'Date',
        'Empire State Basement revenue', 'Long Beach Castle Dungeon revenue',
        'Empire State Basement rent', 'Long Beach Castle Dungeon rent']
    self.assertEqual(row_0, writer.rows[0])
    row_1 = ['2018-03-02', 0, 0, 30.0, 0]
    self.assertEqual(row_1, writer.rows[1])
    row_2 = ['2018-03-03', 50.0, 0, 30.0, 10.0]
    self.assertEqual(row_2, writer.rows[2])
    row_3 = ['2018-03-04', 50.0, 50.0, 30.0, 20.0]
    self.assertEqual(row_3, writer.rows[3])

    writer = FakeWriter()
    write_csv(
        writer, from_date, to_date, interval, COMBINE,
        rental_ids, seriesies)

    self.assertEqual(4, len(writer.rows))
    row_0 = [
        'Date', 'Combined units revenue', 'Combined units rent']
    self.assertEqual(row_0, writer.rows[0])
    row_1 = ['2018-03-02', 0, 30.0]
    self.assertEqual(row_1, writer.rows[1])
    row_2 = ['2018-03-03', 50.0, 40.0]
    self.assertEqual(row_2, writer.rows[2])
    row_3 = ['2018-03-04', 100.0, 50.0]
    self.assertEqual(row_3, writer.rows[3])


class FakeWriter(object):
  def __init__(self):
    self.rows = []

  def writerow(self, row):
    self.rows.append(row)
