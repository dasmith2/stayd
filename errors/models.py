from datetime import timedelta
import traceback

from django.conf import settings
from django.db import models
from django.utils import timezone

from util.email import EmailSender


class ErrorLogger(object):
  """ This class exists so I can Mock it so I can write tests that
  make sure errors get logged the way I want. """
  def log_error(
      self, title, message='', exc_info=None, extra_to=None,
      always_new_error=False):
    return StaydError.objects.log_error(
        title, message, exc_info, extra_to, always_new_error)


def log_error(
    title, message='', exc_info=None, extra_to=None, always_new_error=False):
  """
  try:
    whatever()
  except Exception:
    log_error(
        'I tried to whatever', 'here are some details', sys.exc_info())

  This is the simplest approach, but it's not very friendly for testing.
  """
  return ErrorLogger().log_error(
      title, message=message, exc_info=exc_info, extra_to=extra_to,
      always_new_error=always_new_error)


class Notifier(object):
  def notify(self, to_emails, title, message='', email_sender=EmailSender()):
    StaydNotification.objects.notify(to_emails, title, message, email_sender)


def notify(to, title, message=''):
  return Notifier().notify(to, title, message)


class StaydErrorManager(models.Manager):
  def log_error(self, title, message, exc_info, extra_to, always_new_error):
    value_ = None
    traceback_ = None
    if exc_info:
      type_, value_, traceback_ = exc_info
    stack_trace = ''
    if traceback_:
      stack_trace = '\n'.join(traceback.format_tb(traceback_))

    error_message = ''
    existing = self.filter(
        title=title, created_at__gte=timezone.now() - timedelta(days=1),
        fixed=False)
    if value_:
      error_message = value_.__repr__()
      existing = existing.filter(error_message=error_message)
    if not always_new_error and existing:
      existing = existing[0]
      existing.count += 1
      existing.save()
      return existing

    to_emails = ['heroku-errors@stayd.com']
    if extra_to:
      to_emails.extend(extra_to)

    new_error = self.create(
        title=title,
        count=1,
        message=message,
        error_message=error_message,
        stack_trace=stack_trace,
        to=str(to_emails))

    self._email_error(title, message, to_emails, error_message, stack_trace)

    return new_error

  def _email_error(
      self, title, message, to_emails, error_message, stack_trace):
    email_message = message
    if error_message and stack_trace:
      email_message += '\n\n{}\n\n{}'.format(error_message, stack_trace)
    subject = '{} on {}'.format(title, settings.THIS_SERVERS_BASE_URL)
    EmailSender().send_mail(
        subject, email_message, settings.SERVER_EMAIL, to_emails)


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


class StaydNotificationManager(models.Manager):
  def notify(self, to_emails, title, message, email_sender=EmailSender()):
    """ Log to_emails, title, and message. If it's the first we've seen it
    today, send an email as well. """
    existing = self.filter(
        to=str(to_emails), title=title, message=message,
        created_at__gte=timezone.now() - timedelta(days=1)).first()
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
