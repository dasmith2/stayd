from django.contrib.auth.models import User
from django.utils.timezone import now

from guest_messages.tests import get_test_sms
from util.tests import TestCase
from util.timezone import str_to_tz_dt


class ViewTests(TestCase):
  def test_message_delays(self):
    staff = User.objects.create(username='whatever', is_staff=True)
    self.client.force_login(staff)
    get_test_sms(True, when_should=now(), message='Hello Neptune')
    get_test_sms(
        True, when_should=str_to_tz_dt('2018-10-02 00:00'),
        message='Hello Neptune')
    self.assertGetContains(
        '/message_delays/10-01-2018/11-01-2018', 'Hello Neptune')
