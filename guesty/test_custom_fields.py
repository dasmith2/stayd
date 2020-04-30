import copy
from datetime import date
import json
from unittest.mock import Mock

from djmoney.money import Money

from guesty.custom_fields import GUESTY_MESSAGE_TOGGLE_CUSTOM_FIELDS
from guesty.custom_field_ids import (
    ID_VERIFIED_FIELD_ID, CANARY_IN_THE_COALMINE_FIELD_ID,
    CREDIT_CARD_AUTHORIZATION_VALID_FIELD_ID,
    GUEST_FEEDBACK_FORM_LINK_FIELD_ID, ID_VERIFICATION_LINK_FIELD_ID,
    PAID_IN_FULL_FIELD_ID, IS_TEST_RESERVATION_FIELD_ID,
    PHONE_PROVIDED_FIELD_ID, DEFAULT_GUESTY_FLAG_VALUE)
from guest_messages.tests import get_test_smstemplate, SMS
from guests.models import Guest
from guesty.api_examples import RESERVATION, GUEST
from guesty.custom_fields import CustomFields
from guesty.guesty import (
    Guesty, GuestyAPI, RawEvent)
from guesty.test_models import get_test_guesty_rental
from id_verify.tests import get_test_submission
from rentals.tests import get_test_rental
from reservations.models import Reservation
from reservations.tests import get_test_reservation
from util.tests import TestCase, get_test_user
from util.timezone import str_to_tz_dt


class CanaryInTheCoalmineTests(TestCase):
  """ Guesty's handling of boolean custom fields is prone to errors. I found
  out in a phone convo that their architecture has 3 states: True, False, and
  null. But the user interface has just 2 states: True, False. We have to set
  the default value for all boolean fields per listing. But also the default
  value doesn't aply to imported reservations. I mean, the bugs practically
  write themselves. So now there's one boolean custom field whose whole point
  is to be on. If it's off, eye roll, we hit some bug or another. Just flip all
  boolean fields on for that reservation. """
  def setUp(self):
    super().setUp()
    rental = get_test_rental(alerts_email='alert@stuff.me')
    get_test_guesty_rental(guesty_id='5ade48915ac9b90011ab64cc', rental=rental)
    self.api = Mock(spec=GuestyAPI)
    self.api.get_one.return_value = GUEST
    self.guesty = Guesty(self.api)
    data = copy.deepcopy(RESERVATION)
    self.assertEqual(
        CANARY_IN_THE_COALMINE_FIELD_ID,
        data['customFields'][1]['fieldId'])
    self.canary_custom_field = data['customFields'][1]
    self.webhook_data = {'reservation': data}

  def handle_raw_event_return_sent_custom_fields(self):
    raw = RawEvent.objects.create(
        json=json.dumps(self.webhook_data), event_name='reservation')
    self.guesty.handle_raw_event(raw)
    self.assertEqual(1, Reservation.objects.count())
    url, put_data = self.api.put.call_args_list[0][0]
    return put_data['customFields']

  def test_on_does_not_turn_all_on(self):
    self.canary_custom_field['value'] = True
    custom_fields_data = self.handle_raw_event_return_sent_custom_fields()

    shouldnt_flip_on = []
    for field_id, name in GUESTY_MESSAGE_TOGGLE_CUSTOM_FIELDS:
      shouldnt_flip_on.append(field_id)

    for custom_field in custom_fields_data:
      if custom_field['fieldId'] in shouldnt_flip_on:
        self.fail(custom_field['fieldId'])

  def test_off_turns_all_on(self):
    self.canary_custom_field['value'] = False
    custom_fields_data = self.handle_raw_event_return_sent_custom_fields()

    should_flip_on = [CANARY_IN_THE_COALMINE_FIELD_ID]
    for field_id, name in GUESTY_MESSAGE_TOGGLE_CUSTOM_FIELDS:
      should_flip_on.append(field_id)

    for field_id in should_flip_on:
      value = None
      for custom_field in custom_fields_data:
        if custom_field['fieldId'] == field_id:
          value = custom_field['value']
      self.assertEqual(True, value)


class PushCustomFieldsTests(TestCase):
  def test_push_custom_fields(self):
    r = get_test_reservation(
        maximum_authorization_hold=Money(300, 'USD'),
        issues='What the heck',
        guesty_id='blargh', channel_id='bomkity',
        ideal_payin=Money(100, 'USD'), actual_payin=Money(100, 'USD'))
    get_test_submission(
        reservation=r, id_matches_res=True, cc_matches_id=True,
        cc_matches_payment=True, checked_at=str_to_tz_dt('2018-12-24'),
        checked_by=get_test_user(), birthday=date(2000, 1, 1))
    # Note, confusing, this isn't a MockGuestyAPI.
    api = Mock(spec=GuestyAPI)
    custom_fields = CustomFields(Reservation, 'guesty_id_asdf', [
        {'fieldId': CANARY_IN_THE_COALMINE_FIELD_ID, 'value': True}], api=api)
    custom_fields.push_custom_fields(r)
    cc_auth_field_id = CREDIT_CARD_AUTHORIZATION_VALID_FIELD_ID
    feedback_field_id = GUEST_FEEDBACK_FORM_LINK_FIELD_ID
    feedback_link = r.get_guest_feedback_form_link()
    id_verify_link_field_id = ID_VERIFICATION_LINK_FIELD_ID
    id_verify_link = 'https://verifyid.hihoward.com/verify_id/?id=bomkity'
    expected_custom_fields = [
        {'fieldId': PAID_IN_FULL_FIELD_ID, 'value': True},
        {'fieldId': cc_auth_field_id, 'value': True},
        {'fieldId': feedback_field_id, 'value': feedback_link},
        {'fieldId': id_verify_link_field_id, 'value': id_verify_link},
        {'fieldId': ID_VERIFIED_FIELD_ID, 'value': True},
        {'fieldId': CANARY_IN_THE_COALMINE_FIELD_ID, 'value': True}]
    self.assertEqual(1, len(api.put.call_args_list))
    url, got_custom_fields_data = api.put.call_args_list[0][0]
    got_custom_fields = got_custom_fields_data['customFields']
    for expect in expected_custom_fields:
      found = False
      for got in got_custom_fields:
        if got['fieldId'] == expect['fieldId']:
          found = True
          if expect['value'] != got['value']:
            print('This failure is for fieldId {}'.format(got['fieldId']))
            self.assertEqual(expect['value'], got['value'])
      if not found:
        self.fail('missing {}'.format(expect['fieldId']))


class CustomFieldsTests(TestCase):
  def test_pull_is_test_reservation(self):
    r = get_test_reservation(is_test_reservation=False)
    CustomFields(Reservation, 'guesty_id_whatever', [{
        'fieldId': IS_TEST_RESERVATION_FIELD_ID,
        'value': True}]).pull_custom_fields(r)
    r.refresh_from_db()
    self.assertTrue(r.is_test_reservation)

  def test_pull_custom_fields_for_phone(self):
    r = get_test_reservation(phone='111-111-1111')
    CustomFields(Reservation, 'guesty_id_whatever', [{
        'fieldId': PHONE_PROVIDED_FIELD_ID,
        'value': '222-222-2222'}]).pull_custom_fields(r)
    guest = Guest.objects.get(pk=r.guest.pk)
    self.assertEqual('222-222-2222', guest.phone)
    self.assertTrue(r.guest.has_phone('111-111-1111'))
    self.assertTrue(r.guest.has_phone('222-222-2222'))

  def test_pull_custom_fields_for_id_verified(self):
    r = get_test_reservation(id_verified=False)
    self.assertFalse(r.id_verified)
    custom_fields = CustomFields(Reservation, 'guesty_id_whatever', [{
        'fieldId': ID_VERIFIED_FIELD_ID, 'value': True}])
    custom_fields.pull_custom_fields(r)
    self.assertTrue(Reservation.objects.get(pk=r.pk).id_verified)

  def test_pull_custom_fields_for_messages(self):
    reservation = get_test_reservation(guesty_id='hargenblargen')
    template = get_test_smstemplate(
        guesty_custom_field_id='5afa2c379ebb42009e34f270')
    template.create_new_message(reservation)
    message = SMS.objects.get_for_reservation(reservation)[0]
    self.assertTrue(message.green_light)

    custom_fields = CustomFields(Reservation, 'hargenblargen', [
        {'fieldId': CANARY_IN_THE_COALMINE_FIELD_ID, 'value': True},
        {'fieldId': 'unrelated_field_id', 'value': True}])
    custom_fields.pull_custom_fields(reservation)
    message = SMS.objects.get_for_reservation(reservation)[0]
    self.assertEqual(message.green_light, DEFAULT_GUESTY_FLAG_VALUE)
    self.assertFalse(message.green_light)

    custom_fields = CustomFields(Reservation, 'hargenblargen', [
        {'fieldId': CANARY_IN_THE_COALMINE_FIELD_ID, 'value': True},
        {'fieldId': '5afa2c379ebb42009e34f270', 'value': True}])
    custom_fields.pull_custom_fields(reservation)
    message = SMS.objects.get_for_reservation(reservation)[0]
    self.assertTrue(message.green_light)

    custom_fields = CustomFields(Reservation, 'hargenblargen', [
        {'fieldId': CANARY_IN_THE_COALMINE_FIELD_ID, 'value': True}])
    custom_fields.pull_custom_fields(reservation)
    message = SMS.objects.get_for_reservation(reservation)[0]
    self.assertEqual(message.green_light, DEFAULT_GUESTY_FLAG_VALUE)
    self.assertFalse(message.green_light)
