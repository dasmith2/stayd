from unittest.mock import Mock, call

from django.conf import settings

from front.models import Front, FakeSendSMSResult, DeliveryErrorChecker
from work.models.message import (
    SubjectLine, Message, MessageSender, UNCLAIMED_CLEANING_IN_LT_48_HOURS,
    START_10_MINUTES_LATE, SMS)
from work.tests.test_cleaning import get_test_cleaning
from rentals.tests import get_test_sms_channel
from util.email import EmailSender
from util.tests import TestCase
from util.timezone import str_to_tz_dt


def get_test_subject_line(**kwargs):
  return SubjectLine.objects.create(
      reason=kwargs.get('reason', UNCLAIMED_CLEANING_IN_LT_48_HOURS),
      subject=kwargs.get('subject', 'Warning: unclaimed cleaning'))


def get_test_message(**kwargs):
  work = kwargs.get('work', None)
  if not work:
    work = get_test_cleaning(**kwargs)
  from_channel = kwargs.get('from_channel', None)
  if not from_channel:
    from_channel = get_test_sms_channel(**kwargs)
  return Message.objects.create(
      when=kwargs.get('when', str_to_tz_dt('2018-10-15 12:00')),
      to=kwargs.get('to', 'whoever@email.com'),
      reason=kwargs.get('reason', START_10_MINUTES_LATE),
      kind=kwargs.get('kind', SMS),
      subject=kwargs.get('subject', ''),
      content=kwargs.get('content', 'We just love it when you start on time'),
      delivery_error=kwargs.get('delivery_error', None),
      work=kwargs.get('work', work),
      from_channel=from_channel,
      please_resend_due_to_server_error=kwargs.get(
          'please_resend_due_to_server_error', False),
      server_error_count=kwargs.get('server_error_count', 0))


class CreateAndSendEmailTests(TestCase):
  def test_create_and_send_email(self):
    email_sender = Mock(spec=EmailSender)
    message_sender = MessageSender(email_sender=email_sender)
    cleaning = get_test_cleaning(
        offered_start_time=str_to_tz_dt('2018-12-25 11:15'),
        nickname='Daves')
    message_sender.create_and_send_email(
        'whomever@email.com', START_10_MINUTES_LATE, 'hello world!', cleaning)
    expected_subject = '{}. 2018-12-25 at Daves'.format(START_10_MINUTES_LATE)
    expected = [call(
        expected_subject, 'hello world!', settings.SERVER_EMAIL,
        ['whomever@email.com'], reply_to='')]
    self.assertEqual(expected, email_sender.send_mail.call_args_list)


class MessageSenderTests(TestCase):
  def test_send_sms(self):
    front = Mock(spec=Front)
    front.send_sms.return_value = FakeSendSMSResult()
    message_sender = MessageSender(
        front=front, delivery_error_checker=DeliveryErrorChecker())

    from_sms_channel = get_test_sms_channel(
        name='flies', identifier='on_child')
    work = get_test_cleaning(sms_staff_from=from_sms_channel)
    message_sender.send(
        get_test_message(
            to='666-666-6666', kind=SMS, work=work,
            content='How will I know when Im ready?'))

    self.assertEqual(1, len(front.send_sms.call_args_list))
    (to_phone, content, sms_channel_id) = front.send_sms.call_args_list[0][0]
    self.assertEqual('666-666-6666', to_phone)
    self.assertEqual('How will I know when Im ready?', content)
    self.assertEqual('on_child', sms_channel_id)
