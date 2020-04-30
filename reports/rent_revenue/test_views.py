from rentals.tests import get_test_rental
from reservations.tests import get_test_reservation
from util.tests import TestCase
from util.timezone import str_to_tz_dt


class ViewTests(TestCase):
  def test_rent_revenue(self):
    res = get_test_reservation(
        check_in=str_to_tz_dt('2018-10-21 16:00'),
        check_out=str_to_tz_dt('2018-10-22 11:00'), is_superuser=True)
    self.client.force_login(res.rental.building.owner)
    self.get('/reports/rent_revenue/10-02-2018/11-01-2018')

  def test_csv_options(self):
    self.login(is_superuser=True)
    self.get('/reports/rent_revenue/csv_options')

  def test_csv_download(self):
    self.login(is_superuser=True)
    rental = get_test_rental(nickname='Marcs treehouse')
    get_test_reservation(
        rental=rental, check_in=str_to_tz_dt('2019-01-01 16:00'),
        check_out=str_to_tz_dt('2019-01-02 11:00'))
    url = (
        '/reports/rent_revenue/csv_download?from_date_str=01-01-2019'
        '&to_date_str=03-02-2019&interval=day&rental_ids={}'
        '&series=net').format(rental.pk)
    self.assert_get_contains(url, 'Marcs treehouse')
