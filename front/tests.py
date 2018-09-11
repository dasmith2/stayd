from util.tests import TestCase
from unittest.mock import Mock, call

from errors.models import ErrorLogger
from front.api import FrontAPI
from front.api_examples import (
    MESSAGE, SENT_MESSAGE, CONVERSATION, MESSAGE_WITH_ERROR, INVALID_PHONE,
    INVALID_EMAIL)
from front.models import Front, ContactInfo


class FrontTests(TestCase):
  def test_delivery_error(self):

    class FakeResponse(object):
      ok = True

      def __init__(self, response):
        self.response = response

      def json(self):
        return self.response

    def get_message(message_uid):
      if message_uid == 'bad_message_uid':
        return FakeResponse(MESSAGE_WITH_ERROR)
      elif message_uid == 'good_message_uid':
        return FakeResponse(MESSAGE)
      raise Exception(message_uid)

    front_api = Mock(spec=FrontAPI)
    front_api.get_message.side_effect = get_message
    front = Front(front_api)
    self.assertEqual(
        front.delivery_error(
            {'message_uid': 'bad_message_uid'}), 'twilio_invalid_to')
    self.assertIsNone(
        front.delivery_error({'message_uid': 'good_message_uid'}))

  def test_set_contact_info(self):
    front_api = Mock(spec=FrontAPI)
    front = Front(front_api)
    contact_info = ContactInfo(
        name='Dave',
        description='He\'s pretty rad',
        link='http://whatev',
        phone='+44-098-765-4321',
        email='rad@rad.rad')

    front_api.post_contact.return_value = FakeResponse(
        False, {'_error': {
            'status': 409,
            'title': 'Conflict',
            'message': (
                'Your request contains a conflict with another '
                'contact crd_72m2w5.')}})
    front_api.get_contact.return_value = FakeResponse(True, {})
    front_api.patch_contact.return_value = FakeResponse(True)

    front.set_contact_info(contact_info, ok_to_do_it_in_dev=True)

    self.assertEqual(
        front_api.get_contact.call_args_list,
        [call('crd_72m2w5')])
    expected_patch_data = {
        'name': 'Dave',
        'description': 'He\'s pretty rad',
        'links': ['http://whatev'],
        'handles': [
            {'handle': '+440987654321', 'source': 'phone'},
            {'handle': 'rad@rad.rad', 'source': 'email'}]}
    self.assertEqual(
        front_api.patch_contact.call_args_list,
        [call('crd_72m2w5', expected_patch_data)])

  def test_alert_bad_number(self):
    front_api = Mock(spec=FrontAPI)
    front_api.post_contact.return_value = FakeResponse(False, INVALID_PHONE)

    error_logger = Mock(spec=ErrorLogger)
    front = Front(front_api, error_logger=error_logger)

    contact_info = ContactInfo(
        'Bob', 'The king of Spain', 'http://bob', '123-321-1234',
        'bob@bob.bob')

    for i in range(2):
      front.set_contact_info(contact_info)

    # Only alert once per number.
    self.assertEqual(1, len(error_logger.log_error.call_args_list))
    call = error_logger.log_error.call_args_list[0]
    call_args, call_kwargs = call[0], call[1]  # noqa:F841
    self.assertEqual('Bad phone number probably: 123-321-1234', call_args[0])

  def test_alert_bad_email(self):
    front_api = Mock(spec=FrontAPI)
    front_api.post_contact.return_value = FakeResponse(False, INVALID_EMAIL)

    error_logger = Mock(spec=ErrorLogger)
    front = Front(front_api, error_logger=error_logger)

    contact_info = ContactInfo(
        'Bob', 'The king of Spain', 'http://bob', '123-321-1234',
        'bob@bob.bob')

    for i in range(2):
      front.set_contact_info(contact_info)

    # Only alert once per number.
    self.assertEqual(1, len(error_logger.log_error.call_args_list))
    call = error_logger.log_error.call_args_list[0]
    call_args, call_kwargs = call[0], call[1]  # noqa:F841
    self.assertEqual('Bad email address probably: bob@bob.bob', call_args[0])

  def test_send_sms(self):
    front_api = FakeSMSSender()
    front = Front(front_api)

    front_api.archived = True
    front.send_sms('9176084623', 'Hello world', ok_to_do_it_in_dev=True)
    self.assertEqual(front.get_convo_status('9176084623'), 'archived')
    # Leave the conversation archived, send an SMS, it should stay archived.
    front.send_sms('9176084623', 'Hello venus', ok_to_do_it_in_dev=True)
    self.assertEqual(front.get_convo_status('9176084623'), 'archived')

    # They texted us, and now it's unarchived!
    front_api.archived = False
    # We're going to send an SMS.
    front.send_sms('9176084623', 'Hello mars', ok_to_do_it_in_dev=True)
    # Make sure it sent, and you can see below that this archives.
    # You can also see below that the only way to un-archive is to patch
    # with {'status': 'open'}
    self.assertEqual(front_api.last_send_message['body'], 'Hello mars')
    # But we should still not be archived.
    self.assertEqual(front.get_convo_status('9176084623'), 'assigned')


class FakeResponse(object):
  def __init__(self, ok, json=None):
    self.ok = ok
    self._json = json

  def json(self):
    if self._json is None:
      raise Exception()
    return self._json


class FakeSMSSender(object):
  def __init__(self):
    self.archived = True
    self.last_message_data = None

  def send_message(self, message_data):
    # This is how Front works.
    self.archived = True
    self.last_send_message = message_data
    return FakeResponse(True, SENT_MESSAGE)

  def get_convo(self, convo_id):
    if convo_id != CONVERSATION['id']:
      raise Exception(convo_id)
    status = 'archived' if self.archived else 'assigned'
    return FakeResponse(True, {'status': status})

  def patch_convo(self, convo_id, data):
    if convo_id != CONVERSATION['id']:
      raise Exception(convo_id)
    self.last_patch_convo = data
    # This is how Front works.
    if data['status'] == 'archived':
      self.archived = True
    elif data['status'] == 'open':
      self.archived = False
    else:
      raise Exception()
    return FakeResponse(True)

  def get_message(self, message_uid):
    if message_uid != SENT_MESSAGE['message_uid']:
      raise Exception(message_uid)
    return FakeResponse(True, MESSAGE)
