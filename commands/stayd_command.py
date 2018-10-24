from abc import abstractmethod
import sys

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.timezone import now

from commands.models import CommandRun
from errors.models import log_error
from util.background import background


class StaydCommand(BaseCommand):
  """ Errors in BaseCommands don't have a built in reporting mechanism.
  That's important for management commands that are scheduled to run
  without supervision, such as send_guest_messages. This subclass provides
  that, plus the verbose parameter. """

  @abstractmethod
  def run(self, verbose):
    raise NotImplementedError('run')

  @abstractmethod
  def name(self):
    return '(Please override def name in all subclasses of StaydCommand)'

  def add_arguments(self, parser):
    parser.add_argument(
        '--verbose', action='store_true', dest='verbose')

  def handle(self, *args, **options):
    verbose = options['verbose']
    command_run = CommandRun.objects.create(
        command_name=self.name(), started=now())
    try:
      self.run(verbose)
      command_run.completed = now()
      command_run.save()
    except Exception as ex:
      command_run.error = log_error(
          'manage.py {} error'.format(self.name()), exc_info=sys.exc_info())
      command_run.save()
      if verbose:
        print(
            'There was an error. Check '
            'https://stayd-prod.herokuapp.com/admin/errors/stayderror/')
      if settings.DEBUG:
        raise ex


class ErrorCommand(StaydCommand):
  """ Use this to test error reporting mechanisms. """
  def run(self, verbose):
    print(1 / 0)

  def name(self):
    return 'commands.stayd_command#ErrorCommand'


@background
def run_error_command():
  ErrorCommand().handle(verbose=False)
