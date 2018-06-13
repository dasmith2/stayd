from guesty.models import RawEvent
from commands.stayd_command import StaydCommand


class Command(StaydCommand):
  help = (
      'RawEvents are created when a Guesty webhook runs. They build up '
      'over time so they have to be cleaned up. The command removes '
      'any that are older than 31 days.')

  def run(self, verbose):
    RawEvent.objects.rm_old(days_ago=31, verbose=verbose)

  def name(self):
    return 'rm_old_events'
