from datetime import timedelta

from django.shortcuts import reverse
from django.utils.timezone import now

from reservations.tests import get_test_reservation
from util.channels import AIRBNB
from util.tests import TestCase


class ViewTests(TestCase):
  def test_verify_id(self):
    reservation = get_test_reservation(
        True, full_name='The Queen of England', first_name='The Queen',
        check_in=now() + timedelta(days=2), channel=AIRBNB)
    resp = self.client.get(reservation.verify_id_url_no_server())
    self.assertEqual(resp.status_code, 200)
    find_me = 'The Queen, thanks for booking with STAYD through Airbnb.'
    self.assertTrue(resp.content.decode('utf-8').find(find_me) > 0)

  def test_verify_id_mobile(self):
    self.mobile_client.get(reverse('verify_id'))
