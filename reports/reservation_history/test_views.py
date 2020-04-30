from django.shortcuts import reverse

from reservations.tests import get_test_reservation
from util.tests import TestCase, get_test_user


class ReservationHistoryViewTests(TestCase):
  def test_find_reservation(self):
    reservation = get_test_reservation(full_name='Dave The Rock Johnson')
    user = get_test_user(username='fatima', is_superuser=True)
    self.client.force_login(user)
    url = reverse('reservation_search')
    self.assert_get_contains(url, 'Example searches')
    search_url = url + '?q={}'.format(reservation.pk)
    search_result = self.client.get(search_url)
    self.assertEqual(search_result.status_code, 302)
    self.assert_get_contains(search_result.url, 'Dave The Rock Johnson')

  def test_reservation_history(self):
    reservation = get_test_reservation()
    user = get_test_user()
    self.client.force_login(user)
    url = reverse('reservation_history', kwargs={'pk': reservation.pk})
    self.client.get(url)
