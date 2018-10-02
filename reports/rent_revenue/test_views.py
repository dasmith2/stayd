from reservations.tests import get_test_reservation
from util.tests import TestCase
from util.timezone import str_to_tz_dt


class ViewTests(TestCase):
  def test_rent_revenue(self):
    res = get_test_reservation(
        True, check_in=str_to_tz_dt('2018-10-21 16:00'),
        check_out=str_to_tz_dt('2018-10-22 11:00'))
    self.client.force_login(res.rental.building.owner)
    self.get('/reports/rent_revenue/10-02-2018/11-01-2018')
