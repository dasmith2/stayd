from datetime import timedelta
import traceback

from django.conf import settings
from django.db import models
from django.utils import timezone

from util.email import EmailSender
from util.rm_old import RmOldManager


class ErrorLogger(object):
  """ This class exists so I can Mock it so I can write tests that
  make sure errors get logged the way I want. """
  def log_error(
      self, title, message='', exc_info=None, extra_to=None,
      always_new_error=False, email_sender=None, supress_stack_trace=False):
    return StaydError.objects.log_error(
        title, message, exc_info, extra_to, always_new_error,
        email_sender=email_sender, supress_stack_trace=supress_stack_trace)


def log_error(
    title, message='', exc_info=None, extra_to=None, always_new_error=False,
    email_sender=None, supress_stack_trace=False):
  """
  try:
    whatever()
  except Exception:
    log_error(
        'I tried to whatever', 'here are some details', sys.exc_info())

  This is the simplest approach, but it's not very friendly for testing.

  By default, log_error won't email in the shell. But you can change that if
  you want by doing this in the shell:

  from django.conf import settings
  settings.ALWAYS_ALLOW_SEND_MAIL = True
  from errors.models import log_error
  log_error('hello', 'world')
  """
  return ErrorLogger().log_error(
      title, message=message, exc_info=exc_info, extra_to=extra_to,
      always_new_error=always_new_error, email_sender=email_sender,
      supress_stack_trace=supress_stack_trace)


class Notifier(object):
  def __init__(self, email_sender=None):
    self.email_sender = email_sender

  def notify(self, to_emails, title, message='', email_sender=None):
    email_sender = email_sender or self.email_sender or EmailSender()
    StaydNotification.objects.notify(to_emails, title, message, email_sender)


def notify(to, title, message=''):
  """ `to` can be a string or a list of strings. """
  return Notifier().notify(to, title, message)


class StaydErrorManager(RmOldManager):
  def log_error(
      self, title, message, exc_info, extra_to, always_new_error,
      email_sender=None, supress_stack_trace=False):
    existing = None
    if not always_new_error:
      existing = self.existing_error(title)
      if existing:
        return existing
    new_error = self.create_error(
        title, message, exc_info, extra_to, always_new_error,
        supress_stack_trace=supress_stack_trace)
    self._email_error_obj(new_error, email_sender=email_sender)
    return new_error

  def existing_error(self, title):
    existing = self.filter(
        title=title, created_at__gte=timezone.now() - timedelta(days=1),
        fixed=False).first()
    if existing:
      existing.count += 1
      existing.save()
      if settings.DEBUG:
        print('Incrementing "{}" error count'.format(title))
      return existing

  def create_error(
      self, title, message, exc_info, extra_to, always_new_error,
      supress_stack_trace=False):
    # Just in case somebody passes a tuple in or whatever as the message.
    message = str(message)

    value_ = None
    traceback_ = None
    if exc_info:
      type_, value_, traceback_ = exc_info
    stack_trace = ''
    if supress_stack_trace:
      stack_trace = ''
    elif traceback_:
      stack_trace = '\n'.join(traceback.format_tb(traceback_))
    else:
      stack_trace = '\n'.join([
          line.strip() for line in traceback.format_stack()])

    error_message = ''
    if value_:
      error_message = value_.__repr__()

    to_emails = [settings.EMAIL_ERRORS_TO]
    if extra_to:
      to_emails.extend(extra_to)

    return self.create(
        title=title,
        count=1,
        message=message,
        error_message=error_message,
        stack_trace=stack_trace,
        to=','.join(to_emails))

  def _email_error_obj(self, error, email_sender=None):
    email_sender = email_sender or EmailSender()
    email_message = error.message
    if error.error_message:
      email_message += '\n\n{}'.format(error.error_message)
    if error.stack_trace:
      email_message += '\n\n{}'.format(error.stack_trace)
    subject = '{} on {}'.format(error.title, settings.THIS_SERVERS_BASE_URL)
    if not settings.SERVER_EMAIL or not error.to:
      message = 'settings.SERVER_EMAIL: {}. error.to: {}'.format(
          settings.SERVER_EMAIL, error.to)
      StaydError.objects.create(title=message)
      StaydError.objects.create(title=subject[:250], message=email_message)
    else:
      email_sender.send_mail(
          subject, email_message, settings.SERVER_EMAIL,
          error.to.split(','))


class StaydEmailLog(models.Model):
  title = models.CharField(max_length=250)
  created_at = models.DateTimeField(auto_now_add=True)
  latest_at = models.DateTimeField(auto_now=True)
  count = models.PositiveIntegerField(default=0)
  message = models.TextField(blank=True, default='')
  to = models.TextField(blank=True, default='')

  class Meta:
    abstract = True


class StaydError(StaydEmailLog):
  error_message = models.TextField(blank=True, default='')
  stack_trace = models.TextField(blank=True, default='')
  fixed = models.BooleanField(default=False, help_text=(
      'If you set fixed to True and the error happens again, a new error '
      'will be opened. So you should set this once you THINK you\'ve '
      'fixed it so you\'ll find out if you haven\'t.'))

  objects = StaydErrorManager()


class StaydNotificationManager(RmOldManager):
  def notify(self, to_emails, title, message, email_sender=None):
    """ Log to_emails, title, and message. If it's the first we've seen it
    today, send an email as well. """
    email_sender = email_sender or EmailSender()
    if isinstance(to_emails, str):
      to_emails = [to_emails]
    # I had days=1, but what if you want to send a daily notification? Monday
    # it goes out at 3:01am, Tuesday it tries to go out at 3:00am but it
    # doesn't because it went out within the last day.
    existing = self.filter(
        to=str(to_emails), title=title, message=message,
        created_at__gte=timezone.now() - timedelta(hours=23)).first()
    if existing:
      existing.count += 1
      existing.save()
    else:
      self.create(
          to=str(to_emails), title=title, message=message, count=1)
      email_sender.send_mail(
          title, message, settings.SERVER_EMAIL, to_emails)


class StaydNotification(StaydEmailLog):
  objects = StaydNotificationManager()
