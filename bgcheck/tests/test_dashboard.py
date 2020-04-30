from datetime import date

from bgcheck.models.dashboard import (
    dashboard_table_reservations, dashboard_table, dashboard_totals, detail)
from reservations.tests import get_test_reservation
from util.tests import TestCase
from util.timezone import str_to_tz_dt


class DashboardTests(TestCase):
  def setUp(self):
    super().setUp()
    self.reservation = get_test_reservation(
        check_in=str_to_tz_dt('2018-12-25 16:00'),
        check_out=str_to_tz_dt('2018-12-26 11:00'),
        background_check_guests=True)

  def test_dashboard_table_reservations(self):
    self.assertEqual([self.reservation], list(dashboard_table_reservations(
        date(2018, 12, 25), date(2018, 12, 26))))
    self.assertEqual([], list(dashboard_table_reservations(
        date(2018, 12, 26), date(2018, 12, 27))))

  def test_dashboard_table(self):
    dashboard_table([self.reservation])

  def test_detail(self):
    detail(self.reservation)

  def test_totals(self):
    dashboard_totals([self.reservation])
