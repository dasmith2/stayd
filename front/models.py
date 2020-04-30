"""
The Front API is documented at https://dev.frontapp.com/

Front is our front end for communicating with guests. It's a unified inbox.
It allows a team of people to pretend they're a single person (an avatar,
in other words) responding to any guest who replies to an email or SMS
that we sent via Front.

This file shouldn't know about any business classes like reservations
or whatever. Front gets used by other classes.
"""
import re

from django.conf import settings
from django.db import models
from django.db.models import Q, F

from errors.models import ErrorLogger, log_error, notify
from front.api import FrontAPI
from rentals.models import SMSChannel
from util.background import background
from util.html_status_codes import ServerError, NotOkError


EMAIL = 'email'
PHONE = 'phone'

BAD_GATEWAY_502 = '502 Bad Gateway'
GATEWAY_TIMEOUT_504 = '504 Gateway Timeout'


@background
def sync_sms_channels_background():
  channels = []
  try:
    channels = FrontAPI().get_channels().json()['_results']
  except ServerError:
    pass  # NBD, just let it try again tomorrow.
  for channel in channels:
    if channel['type'] == 'twilio':
      SMSChannel.objects.get_or_create(
          name=channel['name'], identifier=channel['id'])


class FakeSendSMSResult(object):
  ok = True

  def json(self):
    return {'status': 'accepted'}


class BadContactInfoException(Exception):
  def __init__(self, handle_type, sent_data, received_data):
    self.handle_type = handle_type
    self.sent_data = sent_data
    self.received_data = received_data


class DeliveryErrorChecker(object):
  def __init__(self, front_api=FrontAPI(), error_logger=ErrorLogger()):
    self.front_api = front_api
    self.error_logger = error_logger

  def delivery_error(self, send_results):
    """ OK this function is a wreck because who knows what type send_results
    is. You'd better wrap this in a try catch and alert with more context if
    explodes, because it's liable to. """
    if isinstance(send_results, bytes):
      send_results = send_results.decode('utf-8')
      if send_results.find('502 Bad Gateway') >= 0:
        return BAD_GATEWAY_502
      log_error('Unsure how to interpret send results', send_results)
      return 'Some kind of server error probably'
    elif isinstance(send_results, str):
      # This is just to recover from a mistake I made once, storing the error
      # message in SMS send results as opposed to storing the whole response
      # json.
      return send_results
    if hasattr(send_results, 'json'):
      # This just makes it so you can hand the data results from a response or
      # the response itself to this function.
      send_results = send_results.json()
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
      # The match used to be r'(.+) is an invalid recipient for the requested
      # phone channel.' which I'm keeping around for a moment just in case both
      # statuses get returned.
      bad_number_finder = re.compile(r'(.+) is an invalid phone handle.')
      found_bad_number = bad_number_finder.match(details)
      if found_bad_number:
        return 'Front says {} is a bad phone number'.format(
            found_bad_number.group(1))
      else:
        self.error_logger.log_error(
            'Unexpected SMS send results',
            'This doesn\'t contain a message_uid property: {}'.format(
                send_results))


class Front(object):
  def __init__(
      self, front_api=FrontAPI(), testing=False, error_logger=ErrorLogger()):
    self.front_api = front_api
    self.testing = testing
    self.error_logger = error_logger
    self.delivery_error_checker = DeliveryErrorChecker(
        self.front_api, self.error_logger)

  def delivery_error(self, send_results):
    return self.delivery_error_checker.delivery_error(send_results)

  def get_send_sms_data(self, to, content):
    return {'body': content, 'to': [to]}

  def send_sms(self, to, content, from_channel=None, ok_to_do_it_in_dev=False):
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
    data = self.get_send_sms_data(to, content)

    if settings.PROD or ok_to_do_it_in_dev:
      response = self.front_api.send_message(data, from_channel)
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

  def circle_back_around_failed_contact_info_pushes(
      self, verbose=False, ok_to_do_it_in_dev=False):
    for contact_info in ContactInfoNeedsPushing.objects.filter(
        Q(phone='') | ~Q(phone=F('bad_phone')),
        Q(email='') | ~Q(email=F('bad_email'))):
      if verbose:
        print('Retrying {}\'s contact info'.format(contact_info.name))
      if self.set_contact_info(
          contact_info, ok_to_do_it_in_dev=ok_to_do_it_in_dev):
        contact_info.delete()
        if verbose:
          print('Success.')
      elif verbose:
        print('Failed attempt number {}.'.format(contact_info.push_attempts))

  def set_contact_info(self, contact_info, ok_to_do_it_in_dev=False):
    """ Just go ahead and try to make a new contact in Front.
    If it didn't exist yet, that will work, and we're done.
    If that phone number is already in there, you get a 409
    error code with an error message that says the contact id. Patch
    an update to that contact. This approach degrades gracefully when
    the same phone number appears for different guests over time.

    So, there are a number of spots we can, and do, get server errors. When
    those happen, just save contact_info to the database and then
    circle_back_around will retry them.

    Just as a curiosity, you could totally write this by trying to look up
    the contact id first. See the discussion on alt:phone on
    https://dev.frontapp.com/#resource-aliases """
    if contact_info.dont_bother_sending():
      return False

    contact_info.push_attempts += 1
    if contact_info.push_attempts > 3:
      self.error_logger.log_error(
          'Unusually many attempts to save a contact',
          'Contact info pk {}'.format(contact_info.pk))
    if not settings.PROD and not ok_to_do_it_in_dev:
      return True
    sent_data = self._postable_contact_data(contact_info)
    if not sent_data:
      return False
    try:
      first_save = self.front_api.post_contact(sent_data)
    except ServerError:
      # This is, like, their servers are down. Saving the contact_info means
      # that it will just try again later.
      contact_info.save()
      return False
    except NotOkError as ex:
      self.raise_if_invalid_phone_or_email(contact_info, sent_data, ex)
      error_message = self.get_error_message(ex)
      if error_message == 'Plan exceeded.':
        self._handle_payment_required(contact_info)
      else:
        existing_contact_id_finder = re.compile(r'crd_\w+')
        existing_contact_id_finder_found = existing_contact_id_finder.search(
            error_message)
        if existing_contact_id_finder_found:
          return self._handle_contact_conflict(
              existing_contact_id_finder_found.group(), contact_info,
              sent_data)
        else:
          self.error_logger.log_error(
              'I encountered a new Front error message!',
              'code: {}\n\nmessage: {}\n\nposted data: {}'.format(
                  first_save.status_code, error_message, sent_data))
      return False
    # No ServerError? No NotOkError? Then the first save was successful,
    # meaning we created a new contact and we're good to go.
    return True

  def get_error_message(self, not_ok_error):
    return not_ok_error.json()['_error']['message']

  def is_invalid_phone_or_email_error(self, not_ok_error):
    error_message = self.get_error_message(not_ok_error)
    return error_message == 'The request contains an invalid resource'

  def raise_if_invalid_phone_or_email(
      self, contact_info, sent_data, not_ok_error):
    if self.is_invalid_phone_or_email_error(not_ok_error):
      got_data = not_ok_error.json()
      error = got_data['_error']
      details = error['details'][0]  # Yep, it's a list with one thing in it.
      if details.find('phone') >= 0:
        if contact_info:
          contact_info.bad_phone = contact_info.phone
          contact_info.save()
        raise BadContactInfoException(PHONE, sent_data, got_data)
      elif details.find('email') >= 0:
        if contact_info:
          contact_info.bad_email = contact_info.email
          contact_info.save()
        raise BadContactInfoException(EMAIL, sent_data, got_data)
      raise Exception(
          'Not sure how to interpret {}'.format(error), sent_data,
          got_data)

  def _handle_payment_required(self, contact_info):
    contact_info.save()
    notify(
        settings.ALERT_FRONT_PAYMENT_REQUIRED, 'Front requires payment', (
            'The Front API sent us a "Plan exceeded." exception. The last '
            'time this happened it was because we added a new VA seat '
            'which increased the cost of our plan, which we pay yearly.'))

  def _handle_contact_conflict(self, contact_id, contact_info, new_data):
    try:
      loading_data = self.front_api.get_contact(contact_id)
      loading_data_json = loading_data.json()
      loading_data_json.update(new_data)
      self.front_api.patch_contact(contact_id, loading_data_json)
      return True
    except ServerError:
      contact_info.save()
      return False

  def get_convo_status(self, to_phone):
    convo_id = self.get_conversation_id(to_phone)
    if convo_id:
      try:
        gotten_convo = self.front_api.get_convo(convo_id).json()
        if 'status' in gotten_convo:
          return gotten_convo['status']
      except NotOkError as ex:
        if ex.status_code != 404:
          # I think you see {'_error': {'status': 404, 'title': 'Not found'}}
          # when the number changes because the guest provides a new number
          # during the ID validation flow.
          msg = 'to_phone: {}, convo_id: {}, results: {}'.format(
              to_phone, convo_id, ex)
          self.error_logger.log_error(
              'Unexpected result from get_convo(convo_id)', msg)

  def get_conversation_id(self, to_phone):
    convo = Conversation.objects.filter(to_phone=to_phone).first()
    if convo:
      return convo.convo_id

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
    convo_id = self.get_conversation_id(to_phone)
    return self.front_api.patch_convo(convo_id, {'status': 'open'})


class Conversation(models.Model):
  to_phone = models.CharField(db_index=True, max_length=50, help_text=(
      'I assume all conversations are between Stayd and a guest. '
      'This is the phone number that we sent to front in order to '
      'send a message.'))
  convo_id = models.CharField(max_length=50, help_text=(
      'When you fire off a message to somebody, it becomes part of '
      'a conversation.'))


class ContactInfoNeedsPushing(models.Model):
  """ If any of these are saved in the database, that means they were
  unsuccessfully sent to front and must be tried again. Once they are
  successful they should be deleted. """
  name = models.TextField()
  description = models.TextField()
  link = models.TextField()
  phone = models.TextField()
  email = models.TextField()
  bad_phone = models.TextField(default='', help_text=(
      'If front was unhappy with the phone number, save the bad phone number '
      'here. Then we can compare it to the phone number, and if it\'s '
      'unchanged, don\'t bother trying to send it to front.'))
  bad_email = models.TextField(default='', help_text=(
      'If front was unhappy with the email number, save the bad email address '
      'here. Then we can compare it to the email, and if it\'s '
      'unchanged, don\'t bother trying to send it to front.'))
  push_attempts = models.PositiveIntegerField(default=0)

  def dont_bother_sending(self):
    return (self.phone and self.phone == self.bad_phone) or (
        self.email and self.email == self.bad_email)

  def equals(self, other):
    return all([
        self.name == other.name,
        self.description == other.description,
        self.link == other.link,
        self.phone == other.phone,
        self.email == other.email])

  def push(self):
    return Front().set_contact_info(self)

  def __repr__(self):
    return '<ContactInfoNeedsPushing({}, {}, {}, {}, {})>'.format(
        self.name, self.description, self.link, self.phone, self.email)
