import sys
from unittest.mock import Mock, call

from django.conf import settings

from errors.models import log_error, StaydError, Notifier, StaydNotification
from util.email import EmailSender
from util.tests import TestCase


class LogErrorTests(TestCase):
  def test_log_error(self):
    b = {}
    for i in range(2):
      try:
        b['hello!']
      except Exception:
        log_error(
            'a = b?!', 'here are some details', sys.exc_info())
    stayd_error = StaydError.objects.get(title='a = b?!')
    self.assertEqual(2, stayd_error.count)
    self.assertEqual(stayd_error.message, 'here are some details')
    self.assertEqual(
        stayd_error.error_message, 'KeyError(\'hello!\',)')
    self.assertTrue(bool(stayd_error.stack_trace))

    stayd_error.fixed = True
    stayd_error.save()

    try:
      b['hello!']
    except Exception:
      log_error(
          'a = b?!', 'here are some details', sys.exc_info())
    errors = StaydError.objects.filter(title='a = b?!').order_by('pk')
    self.assertEqual(2, errors.count())
    self.assertTrue(errors[0].fixed)
    self.assertFalse(errors[1].fixed)


class NotificationTests(TestCase):
  def test_notify(self):
    email_sender = Mock(spec=EmailSender)
    self.assertEqual(0, StaydNotification.objects.count())
    for i in range(2):
      Notifier().notify(
          ['a@email.com'], 'title here', 'message here', email_sender)
    self.assertEqual(1, len(email_sender.send_mail.call_args_list))
    self.assertEqual(call(
        'title here', 'message here', settings.SERVER_EMAIL,
        ['a@email.com']), email_sender.send_mail.call_args_list[0])
    self.assertEqual(1, StaydNotification.objects.count())
    notification = StaydNotification.objects.first()
    self.assertEqual(notification.title, 'title here')
    self.assertEqual(notification.count, 2)
    self.assertEqual(notification.message, 'message here')
    self.assertEqual(notification.to, "['a@email.com']")
