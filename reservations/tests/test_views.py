from django.shortcuts import reverse
from djmoney.money import Money

from reservations.models import CANCELED
from reservations.tests import get_test_reservation
from util.tests import TestCase
from util.timezone import str_to_tz_dt


class ViewTester(TestCase):
  def get_balance_due(self):
    return get_test_reservation(
        guesty_id='f',
        check_in=str_to_tz_dt('2018-11-01 16:00'),
        check_out=str_to_tz_dt('2018-11-02 11:00'),
        actual_payin=Money('43.21', 'USD'),
        ideal_payin=Money('10.98', 'USD'), status=CANCELED,
        canceled_at=str_to_tz_dt('2018-10-16 12:00'),
        first_name='Pizza', last_name='Steve', full_name='Pizza Steve')

  def test_likely_payin_not_ideal_payin(self):
    self.get_balance_due()
    self.login(is_superuser=True)
    url = reverse('unresolved_likely_payin_not_ideal')
    self.assert_get_contains(url, 'Pizza Steve')
    url = reverse('unresolved_likely_payin_not_ideal_csv')
    self.assert_get_contains(url, 'Pizza Steve')

  def test_resolve_payin(self):
    self.login(is_superuser=True)
    url = reverse('resolve_payin', kwargs={'pk': self.get_balance_due().pk})
    self.assert_get_contains(url, 'Pizza Steve')
