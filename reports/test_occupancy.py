from datetime import date

from django.shortcuts import reverse

from stats.models.stale import Stale
from rentals.tests import get_test_rental
from reservations.tests import get_test_reservation
from reports.occupancy import get_occupancy
from util.tests import TestCase
from util.timezone import str_to_tz_dt


class OccupancyTests(TestCase):
  def test_get_occupancy(self):
    # The first week is totally empty. The second week totally full.
    nnow = str_to_tz_dt('2019-01-15 12:00')
    rental = get_test_rental(nickname='Daves place')
    reservation = get_test_reservation(
        rental=rental, check_in=str_to_tz_dt('2019-01-22 16:00'),
        check_out=str_to_tz_dt('2019-01-29 11:00'))

    Stale.objects.mark_stale_due_to_reservation(reservation)
    Stale.objects.fix()

    occupancy = get_occupancy(nnow)
    self.assertEqual(date(2019, 1, 15), occupancy.headers[0].week)
    self.assertEqual('Jan 15, 0 days out', occupancy.headers[0].label)
    self.assertEqual(85, occupancy.headers[0].ideal)
    self.assertEqual(1, len(occupancy.occupancy_rows))
    row = occupancy.occupancy_rows[0]
    self.assertEqual('Daves place', row.nickname)
    # Pink. Underbooked.
    self.assertEqual('f3f', row.occupancy_cells[0].color)
    self.assertEqual(0, row.occupancy_cells[0].occupancy)
    # Green. Overbooked.
    self.assertEqual('cfc', row.occupancy_cells[1].color)
    self.assertEqual(100, row.occupancy_cells[1].occupancy)

    # As long as we're here...
    self.login(is_superuser=True)
    url = reverse('occupancy_lookahead') + '?nnow=2019-01-15 12:00'
    self.assert_get_contains(url, 'Daves place')
