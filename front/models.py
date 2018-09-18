"""
The Front API is documented at https://dev.frontapp.com/

Front is our front end for communicating with guests. It's a unified inbox.
It allows a team of people to pretend they're a single person (an avatar,
in other words) responding to any guest who replies to an email or SMS
that we sent via Front.

This file shouldn't know about any business classes like reservations
or whatever. Front gets used by other classes.
"""

from collections import namedtuple
import re

from django.conf import settings
from django.db import models

from errors.models import ErrorLogger
from front.api import FrontAPI
from util.api_500 import is_server_error


EMAIL = 'email'
PHONE = 'phone'


class FakeSendSMSResult(object):
  ok = True

  def json(self):
    return {'status': 'accepted'}


class BadContactInfoException(Exception):
  def __init__(self, handle_type, sent_data, received_data):
    self.handle_type = handle_type
    self.sent_data = sent_data
    self.received_data = received_data


class Front(object):
  def __init__(
      self, front_api=FrontAPI(), testing=False, error_logger=ErrorLogger()):
    self.front_api = front_api
    self.testing = testing
    self.error_logger = error_logger

  def delivery_error(self, send_results):
    if 'message_uid' in send_results:
      message_uid = send_results['message_uid']
      msg_response = self.front_api.get_message(message_uid)
      if not msg_response.ok:
        raise Exception(msg_response)
      msg = msg_response.json()
      if 'error_type' in msg and msg['error_type']:
        return msg['error_type']
    else:
      details_list = send_results.get('_error', {}).get('details', [])
      details = ''
      if details_list:
        details = details_list[0]
      bad_number_finder = re.compile(
          r'(.+) is an invalid recipient for the requested phone channel.')
      found_bad_number = bad_number_finder.match(details)
      if found_bad_number:
        return 'Front says {} is a bad phone number'.format(
            found_bad_number.group(1))
      else:
        self.error_logger.log_error(
            'Unexpected SMS send results',
            'This doesn\'t contain a message_uid property: {}'.format(
                send_results))

  def _postable_contact_data(self, contact_info):
    handles = []
    if contact_info.phone:
      strip_non_phone = re.compile(r'[^\d+]')
      handles.append({
          'handle': strip_non_phone.sub('', contact_info.phone),
          'source': 'phone'})
    # Sometimes there is no email and Front complains if you send an empty
    # handle.
    if contact_info.email:
      handles.append(
          {'handle': contact_info.email, 'source': 'email'})
    if not handles:
      # A contact must have at least one handle.
      return
    return {
        'name': contact_info.name,
        'description': contact_info.description,
        'links': [contact_info.link],
        'handles': handles}

  def set_contact_info(self, contact_info, ok_to_do_it_in_dev=False):
    """ Just go ahead and try to make a new contact in Front.
    If it didn't exist yet, that will work, and we're done.
    If that phone number is already in there, you get a 409
    error code with an error message that says the contact id. Patch
    an update to that contact. This approach degrades gracefully when
    the same phone number appears for different guests over time.

    Just as a curiosity, you could totally write this by trying to look up
    the contact id first. See the discussion on alt:phone on
    https://dev.frontapp.com/#resource-aliases """
    if not settings.PROD and not ok_to_do_it_in_dev:
      return True
    new_data = self._postable_contact_data(contact_info)
    if not new_data:
      return False
    first_save = self.front_api.post_contact(new_data)
    if first_save.ok:
      return True
    if is_server_error(first_save):
      self.error_logger.log_error(
          'Front server error (first_save).',
          'I could really use a redo mechanism. {}\n\n{}'.format(
              first_save.status_code, first_save.content))
      return
    error = first_save.json()['_error']
    error_message = error['message']
    message_finder = re.compile(r'crd_\w+')
    message_found = message_finder.search(error_message)
    if not message_found:
      invalid_resource = error_message == (
          'The request contains an invalid resource')
      if invalid_resource:
        details = error['details'][0]  # Yep, it's a list with one thing in it.
        if details.find('phone') >= 0:
          raise BadContactInfoException(PHONE, new_data, first_save.json())
        elif details.find('email') >= 0:
          raise BadContactInfoException(EMAIL, new_data, first_save.json())
      self.error_logger.log_error(
          'Couldn\'t find existing contact id in error message',
          'code: {}\n\nmessage: {}\n\nposted data: {}'.format(
              first_save.status_code, error_message, new_data))
      return False
    contact_id = message_found.group()
    loading_data = self.front_api.get_contact(contact_id)
    if is_server_error(loading_data):
      self.error_logger.log_error(
          'Front server error (loading_data).',
          'I could really use a redo mechanism. {}\n\n{}'.format(
              loading_data.status_code, loading_data.content))
      return
    loaded_data = loading_data.json()
    loaded_data.update(new_data)
    patching = self.front_api.patch_contact(contact_id, loaded_data)
    if is_server_error(patching):
      self.error_logger.log_error(
          'Front server error (patching).',
          'I could really use a redo mechanism. {}\n\n{}'.format(
              patching.status_code, patching.content))
      return
    return patching.ok and contact_id

  def send_sms(self, to, content, ok_to_do_it_in_dev=False):
    """
    It's ok_to_do_it_in_dev when the front_api is mocked, you're testing
    manually in a shell, or you're using the workflow where you send a
    test SMS to yourself on the SMS templates admin page.

    In front, conversations can have three statuses that I know of.
    unassigned, assigned, and archived. In Front, when we send an SMS to
    somebody, that automatically archives the conversation. When they reply,
    that un-archives it. Here's what we WANT to happen. When we send messages,
    whether or not the convo is archived shouldn't change. Imagine somebody
    SMS-ed us a problem with the apartment, the "How's everything at the apt?"
    auto-SMS went out, that archived the conversation, and we never saw the
    complaint. That guest would hate us for not listening. So. We need to
    keep track of the convo_id per phone number so we can check the status
    of the convo before we send. Then when we send the message and it's
    auto-archived, we can un-archive it when appropriate. """
    convo_status = self.get_convo_status(to)
    data = {
        'body': content,
        'to': [to]}

    if settings.PROD or ok_to_do_it_in_dev:
      response = self.front_api.send_message(data)
      if not response.ok:
        return response
      if convo_status:
        if convo_status != 'archived':
          self._unarchive_convo(to)
      else:
        self._create_conversation(to, response.json())
      return response
    elif self.testing:
      return FakeSendSMSResult()
    elif settings.DEBUG:
      print('')
      print(to)
      print(content)
      print('')
      return FakeSendSMSResult()
    elif settings.STAGE:
      pass
    else:
      raise Exception('Some unexpected pathway is trying to send SMSs!')

  def get_convo_status(self, to_phone):
    convo = self._get_conversation(to_phone)
    if convo:
      gotten_convo = self.front_api.get_convo(convo.convo_id).json()
      if 'status' in gotten_convo:
        return gotten_convo['status']
      elif gotten_convo.get('_error', {}).get('status', 0) != 404:
        # I think you see {'_error': {'status': 404, 'title': 'Not found'}}
        # in gotten_convo when the number changes because the guest
        # provides a new number during the ID validation flow.
        msg = 'to_phone: {}, convo_id: {}, results: {}'.format(
            to_phone, convo.convo_id, gotten_convo)
        self.error_logger.log_error(
            'Unexpected result from get_convo(convo_id)', msg)

  def _get_conversation(self, to_phone):
    return Conversation.objects.filter(to_phone=to_phone).first()

  def _create_conversation(self, to_phone, sms_sent_json):
    """ See front/api_examples.py SENT_MESSAGE """
    message_uid = sms_sent_json['message_uid']
    message = self.front_api.get_message(message_uid).json()
    if '_links' in message:
      convo_url = message['_links']['related']['conversation']
      convo_id = re.compile(r'cnv_\w+').search(convo_url).group()
      Conversation.objects.create(to_phone=to_phone, convo_id=convo_id)
    else:
      self.error_logger.log_error(
          'Unexpected result from get_message(message_uid)',
          'sms_sent_json: {}\n\nmessage_uid: {}\n\nmessage: {}'.format(
              sms_sent_json, message_uid, message))

  def _unarchive_convo(self, to_phone):
    convo = self._get_conversation(to_phone)
    return self.front_api.patch_convo(convo.convo_id, {'status': 'open'})


class Conversation(models.Model):
  to_phone = models.CharField(db_index=True, max_length=50, help_text=(
      'I assume all conversations are between Stayd and a guest. '
      'This is the phone number that we sent to front in order to '
      'send a message.'))
  convo_id = models.CharField(max_length=50, help_text=(
      'When you fire off a message to somebody, it becomes part of '
      'a conversation.'))


class ContactInfo(
    namedtuple('ContactInfo', 'name description link phone email')):
  pass
