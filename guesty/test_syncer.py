from datetime import timedelta
from unittest.mock import Mock, call

from django.conf import settings
from django.utils.timezone import now

from guesty.api_getter import GuestyAPIGetter
from guesty.syncer import Syncer
from reservations.tests import get_test_reservation
from util.tests import TestCase


class SyncerTests(TestCase):
  def test_set_phone_email(self):
    api_getter = Mock(spec=GuestyAPIGetter)
    api_getter.get_one.return_value = {'customFields': []}
    syncer = Syncer(api_getter=api_getter)

    reservation = get_test_reservation(
        True, full_name='The Queen', check_in=now() + timedelta(days=2),
        guesty_id='blahblahbluesheep')

    syncer.set_phone_email(reservation, '555-666-7789', 'the_queen@gmail.com')

    expected_fields = [{
        'fieldId': settings.EMAIL_PROVIDED_FIELD_ID,
        'value': 'the_queen@gmail.com'}, {
        'fieldId': settings.PHONE_PROVIDED_FIELD_ID,
        'value': '555-666-7789'}, {
        'fieldId': settings.COMPLETE_ID_VERIFICATION_EMAIL_FIELD_ID,
        'value': False}]

    self.assertEqual(
        api_getter.put.call_args_list,
        [call(
            'reservations/blahblahbluesheep',
            {"customFields": expected_fields})])
