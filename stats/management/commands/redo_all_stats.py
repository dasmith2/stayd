from commands.stayd_command import StaydCommand
from stats.models import Stale


class Command(StaydCommand):
  def run(self, verbose):
    Stale.objects.mark_all_stats_stale(verbose=verbose)
    Stale.objects.fix(verbose=verbose)

  def name(self):
    return 'redo_all_stats'
