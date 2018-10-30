import sys

from django.conf import settings
from django.db import models
from django.utils.timezone import now

from errors.models import StaydError, log_error
from util.background import background
from util.email import EmailSender


class CommandRun(models.Model):
  command_name = models.CharField(max_length=200)
  started = models.DateTimeField()
  completed = models.DateTimeField(null=True, blank=True)
  error = models.ForeignKey(
      StaydError, null=True, blank=True, on_delete=models.CASCADE)


def background_command(command_name):
  """ This is getting awfully magical, but here we go. This is a decorator with
  a parameter that a) runs your code in the background and b) logs the start
  time, end time, and when applicable, error to the CommandRun table.
  https://stackoverflow.com/questions/5929107/decorators-with-parameters
  See properly.commands for examples.
  """
  def real_decorator(func):
    def func_wrapper(*args, **kwargs):
      command_run = CommandRun.objects.create(
          command_name=command_name, started=now())
      try:
        func(*args, **kwargs)
        command_run.completed = now()
        command_run.save()
      except Exception as ex:
        command_run.error = log_error(
            '{} error'.format(command_name), exc_info=sys.exc_info())
        command_run.save()
    return background(func_wrapper)
  return real_decorator


@background_command('Test error')
def test_error():
  print(1 / 0)


@background_command('Test email')
def test_email():
  EmailSender().send_mail(
      'Test background command email', 'Hey it worked!', settings.SERVER_EMAIL,
      ['dave@stayd.com'])
