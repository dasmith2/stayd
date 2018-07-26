from django.shortcuts import reverse

from reservations.tests import get_test_reservation
from util.tests import TestCase, get_test_user


class ReservationHistoryViewTests(TestCase):
  def test_find_reservation(self):
    reservation = get_test_reservation(
        True, full_name='Dave The Rock Johnson')
    user = get_test_user(True, username='fatima')
    self.client.force_login(user)
    self.assertGetContains(
        reverse('reservation_search'), 'Example searches')
    search_url = reverse('reservation_search') + '?q={}'.format(reservation.pk)
    search_result = self.client.get(search_url)
    self.assertEqual(search_result.status_code, 302)
    self.assertGetContains(search_result.url, 'Dave The Rock Johnson')
