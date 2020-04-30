from datetime import timedelta
from unittest.mock import Mock, call

from util.timezone import now

from guesty.api import GuestyAPI
from guesty.custom_field_ids import (
    ID_VERIFIED_FIELD_ID, EMAIL_PROVIDED_FIELD_ID, PHONE_PROVIDED_FIELD_ID,
    COMPLETE_ID_VERIFICATION_EMAIL_FIELD_ID, RISK_SCORE_FIELD_ID)
from guesty.syncer import Syncer
from reservations.tests import get_test_reservation
from util.tests import TestCase


class SyncerTests(TestCase):
  """ The Syncer is that generic interface to abstract away guesty. """
  def setUp(self):
    super().setUp()
    self.api = Mock(spec=GuestyAPI)
    self.api.get_one.return_value = {'customFields': []}
    self.syncer = Syncer(api=self.api)

    self.reservation = get_test_reservation(
        full_name='The Queen', check_in=now() + timedelta(days=2),
        check_out=now() + timedelta(days=4),
        guesty_id='blahblahbluesheep')

  def test_set_phone_email(self):
    self.syncer.set_phone_email(
        self.reservation, '555-666-7789', 'the_queen@gmail.com')

    expected_fields = [{
        'fieldId': EMAIL_PROVIDED_FIELD_ID,
        'value': 'the_queen@gmail.com'}, {
        'fieldId': PHONE_PROVIDED_FIELD_ID,
        'value': '555-666-7789'}, {
        'fieldId': COMPLETE_ID_VERIFICATION_EMAIL_FIELD_ID,
        'value': False}]

    self.assertEqual(
        self.api.put.call_args_list, [call('reservations/blahblahbluesheep', {
            'customFields': expected_fields})])

  def test_set_id_verified(self):
    self.syncer.set_id_verified(self.reservation)

    expected_fields = [{'fieldId': ID_VERIFIED_FIELD_ID, 'value': True}]

    self.assertEqual(
        self.api.put.call_args_list, [call('reservations/blahblahbluesheep', {
            'customFields': expected_fields})])

  def test_set_risk_score(self):
    self.syncer.set_risk_score(self.reservation, -5)

    expected_fields = [{'fieldId': RISK_SCORE_FIELD_ID, 'value': -5}]

    self.assertEqual(
        self.api.put.call_args_list, [call('reservations/blahblahbluesheep', {
            'customFields': expected_fields})])
