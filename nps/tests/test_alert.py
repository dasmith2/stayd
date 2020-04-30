from unittest.mock import Mock, call

from django.conf import settings

from errors.models import Notifier
from nps.models.alert import post_save_rating
from nps.tests.test_rating import get_test_rating
from util.tests import TestCase


class NotificationTests(TestCase):
  def test_notify(self):
    rating = get_test_rating(
        nickname='Dudes Donuts', full_name='Angry Alice', score=5,
        guesty_id='abba')

    notifier = Mock(spec=Notifier)
    for i in range(2):
      post_save_rating(None, rating, notifier=notifier)
    post_save_rating(None, get_test_rating(score=10), notifier=notifier)

    title = 'Detractor at Dudes Donuts'
    message = (
        'Angry Alice rated us 5\n\n'
        'https://app.guesty.com/reservations/abba/guests')
    expected = call(settings.ALERT_NPS_DETRACTOR, title, message)
    self.assertEqual([expected], notifier.notify.call_args_list)
