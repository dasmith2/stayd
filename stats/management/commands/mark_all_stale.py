from commands.stayd_command import StaydCommand
from stats.models import Stale


class Command(StaydCommand):
  def run(self, verbose):
    Stale.objects.mark_all_stale(verbose=verbose)

  def name(self):
    return 'mark_all_stale'
