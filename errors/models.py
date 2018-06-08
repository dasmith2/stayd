from datetime import timedelta
import traceback

from django.conf import settings
from django.core.mail import send_mail
from django.db import models
from django.utils import timezone


class ErrorLogger(object):
  """ This class exists so I can Mock it so I can write tests that
  make sure errors get logged the way I want. """
  def log_error(self, title, message='', exc_info=None):
    value_ = None
    traceback_ = None
    if exc_info:
      type_, value_, traceback_ = exc_info
    return StaydError.objects.log_error(title, message, value_, traceback_)


def log_error(title, message='', exc_info=None):
  """
  try:
    whatever()
  except Exception:
    log_error(
        'I tried to whatever', 'here are some details', sys.exc_info())
  """
  ErrorLogger().log_error(title, message=message, exc_info=exc_info)


class StaydErrorManager(models.Manager):
  def log_error(self, title, message, value_, traceback_):
    error_message = ''
    existing = self.filter(
        title=title, created_at__gte=timezone.now() - timedelta(days=1),
        fixed=False)
    if value_:
      error_message = value_.__repr__()
      existing = existing.filter(error_message=error_message)
    if existing:
      existing = existing[0]
      existing.count += 1
      existing.save()
    else:
      stack_trace = ''
      if traceback_:
        stack_trace = '\n'.join(traceback.format_tb(traceback_))
      self.create(
          title=title,
          count=1,
          message=message,
          error_message=error_message,
          stack_trace=stack_trace)
      email_message = message
      if error_message and stack_trace:
        email_message += '\n\n{}\n\n{}'.format(error_message, stack_trace)
      subject = '{} on {}'.format(title, settings.THIS_SERVERS_BASE_URL)
      if settings.DEBUG:
        print()
        print(subject)
        print(email_message)
        print()
      else:
        send_mail(
            subject, email_message, 'heroku@stayd.com',
            ['heroku-errors@stayd.com'], fail_silently=False)


class StaydError(models.Model):
  title = models.CharField(max_length=250)
  created_at = models.DateTimeField(auto_now_add=True)
  latest_at = models.DateTimeField(auto_now=True)
  count = models.PositiveIntegerField(default=0)
  message = models.TextField(blank=True, default='')
  error_message = models.TextField(blank=True, default='')
  stack_trace = models.TextField(blank=True, default='')
  fixed = models.BooleanField(default=False, help_text=(
      'If you set fixed to True and the error happens again, a new error '
      'will be opened. So you should set this once you THINK you\'ve '
      'fixed it so you\'ll find out if you haven\'t.'))

  objects = StaydErrorManager()
