from datetime import timedelta

from django.shortcuts import reverse
from django.utils.timezone import now

from id_verify.tests import get_checkable_submission
from reservations.tests import get_test_reservation
from util.channels import AIRBNB
from util.tests import TestCase, get_test_user


class ViewTests(TestCase):
  def test_verify_id(self):
    reservation = get_test_reservation(
        True, full_name='The Queen of England', first_name='The Queen',
        check_in=now() + timedelta(days=2), channel=AIRBNB)
    self.assertGetContains(
        reservation.verify_id_url_no_server(),
        'The Queen, thanks for booking with STAYD through Airbnb.')

  def test_verify_id_mobile(self):
    self.mobile_client.get(reverse('verify_id'))

  def test_submissions(self):
    get_checkable_submission(True, full_name='Bob Schmob', last_name='Schmob')

    not_in_id_verify = get_test_user(True, username='fatima')
    in_id_verify = get_test_user(True, username='bob', groups=['id_verify'])

    self.client.force_login(not_in_id_verify)
    self.assertGetContains(
        reverse('submissions'),
        'You need to be a member of the id_verify group')

    self.client.force_login(in_id_verify)

    url = reverse('submissions')
    self.assertGetContains(url, 'Schmob')
