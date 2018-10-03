from commands.stayd_command import StaydCommand
from stats.models import Stale


class Command(StaydCommand):
  def run(self, verbose):
    Stale.objects.redo_all_stats(verbose=verbose)

  def name(self):
    return 'redo_all_stats'
