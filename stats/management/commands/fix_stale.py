from commands.stayd_command import StaydCommand
from stats.models import Stale
from util.background import background


class Command(StaydCommand):
  def run(self, verbose):
    Stale.objects.fix(verbose=verbose)

  def name(self):
    return 'fix_stale'


@background
def run_fix_stale_background():
  Command().handle()
