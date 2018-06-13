from django.test import TestCase

from commands.models import CommandRun
from commands.stayd_command import StaydCommand


class StaydCommandTests(TestCase):
  def test_two_bad_runs(self):
    bad_command = BadCommand()
    bad_command.handle(verbose=False)
    bad_command.handle(verbose=False)
    bad_runs = CommandRun.objects.filter(command_name='BadCommand')

    self.assertEqual(2, len(bad_runs))
    self.assertTrue(bool(bad_runs[0].error))
    self.assertEqual(bad_runs[0].error.pk, bad_runs[1].error.pk)
    self.assertIsNone(bad_runs[0].completed)

  def test_good_run(self):
    good_command = GoodCommand()
    good_command.handle(verbose=False)
    good_runs = CommandRun.objects.filter(command_name='GoodCommand')
    self.assertEqual(1, len(good_runs))
    good_run = good_runs[0]
    self.assertTrue(bool(good_run.completed))
    self.assertIsNone(good_run.error)


class GoodCommand(StaydCommand):
  def run(self, verbose):
    pass

  def name(self):
    return 'GoodCommand'


class BadCommand(StaydCommand):
  def run(self, verbose):
    raise Exception('Oh boy, failed again?!')

  def name(self):
    return 'BadCommand'
