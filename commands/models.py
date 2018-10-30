import sys

from django.conf import settings
from django.db import models
from django.utils.timezone import now
from rq import Queue

from errors.models import StaydError, log_error
from util.email import EmailSender
from util.rm_old import RmOldManager
from worker import conn


# The default default_timeout is 2 minutes. This makes it an hour.
q = Queue(connection=conn, default_timeout=60 * 60)


class CommandRunManager(RmOldManager):
  pass


class CommandRun(models.Model):
  command_name = models.CharField(max_length=200)
  started = models.DateTimeField()
  completed = models.DateTimeField(null=True, blank=True)
  error = models.ForeignKey(
      StaydError, null=True, blank=True, on_delete=models.CASCADE)
  created_at = models.DateTimeField(auto_now_add=True)

  objects = CommandRunManager()

  class Meta:
    ordering = ('-started',)


def background_command(func):
  """ Use this decorator on a function that's probably kicked off by clock.py
  This a) runs your code in the background and b) logs the start time, end
  time, and when applicable, error to the CommandRun table. """
  def func_wrapper(*args, **kwargs):
    command_name = func.__name__
    if settings.TEST or settings.DEBUG or settings.BACKGROUND:
      command_run = CommandRun.objects.create(
          command_name=command_name, started=now())
      try:
        func(*args, **kwargs)
        command_run.completed = now()
      except Exception as ex:
        command_run.error = log_error(
            '{} error'.format(command_name), exc_info=sys.exc_info())
      command_run.save()
    else:
      # Otherwise we're on web or something and we wanna kick this function
      # off to a background thread.
      q.enqueue(func, *args, **kwargs)
  return func_wrapper


@background_command
def test_error():
  print(1 / 0)


@background_command
def test_email():
  EmailSender().send_mail(
      'Test background command email', 'Hey it worked!', settings.SERVER_EMAIL,
      ['dave@stayd.com'])
