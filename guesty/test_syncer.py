from datetime import timedelta
from unittest.mock import Mock, call

from django.conf import settings
from django.utils.timezone import now

from guesty.api import GuestyAPI
from guesty.syncer import Syncer
from reservations.tests import get_test_reservation
from util.channels import BOOKINGCOM
from util.tests import TestCase


class SyncerTests(TestCase):
  """ The Syncer is that generic interface to abstract away guesty. """
  def test_set_phone_email(self):
    api = Mock(spec=GuestyAPI)
    api.get_one.return_value = {'customFields': []}
    syncer = Syncer(api=api)

    reservation = get_test_reservation(
        True, full_name='The Queen', check_in=now() + timedelta(days=2),
        check_out=now() + timedelta(days=4),
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
        api.put.call_args_list,
        [call(
            'reservations/blahblahbluesheep',
            {"customFields": expected_fields})])

  def test_set_id_verified(self):
    api = Mock(spec=GuestyAPI)
    api.get_one.return_value = {'customFields': []}
    syncer = Syncer(api=api)

    reservation = get_test_reservation(
        True, check_in=now() + timedelta(days=2),
        check_out=now() + timedelta(days=4), channel=BOOKINGCOM,
        guesty_id='booboogreencow')

    syncer.set_id_verified(reservation)

    fields = [{
        'fieldId': settings.ID_VERIFIED_FIELD_ID,
        'value': True}]
    self.assertEqual(
        api.put.call_args_list,
        [call('reservations/booboogreencow', {'customFields': fields})])
