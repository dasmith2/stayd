"""
See also util/rm_old.py
"""
from commands.stayd_command import StaydCommand
from errors.models import StaydError, StaydNotification
from guest_messages.models.models import RawMandrillEvent
from guesty.models import RawEvent as GuestyEvent
from performance.models import LongRequest
from properly.models import RawEvent as ProperlyEvent
from stats.models import OldStale
from util.background import background


class Command(StaydCommand):
  help = (
      'RawEvents are created when a Guesty webhook runs. They build up '
      'over time so they have to be cleaned up. The command removes '
      'any that are older than 31 days.')

  def run(self, verbose):
    # One time I needed some of these that were 45 days old, so, they were
    # gone because the default is 31.
    GuestyEvent.objects.rm_old(verbose=verbose)
    RawMandrillEvent.objects.rm_old(verbose=verbose)
    LongRequest.objects.rm_old(verbose=verbose)
    ProperlyEvent.objects.rm_old(verbose=verbose)
    OldStale.objects.rm_old(verbose=verbose)
    StaydError.objects.rm_old(verbose=verbose)
    StaydNotification.objects.rm_old(verbose=verbose)

  def name(self):
    return 'rm_old_events'


@background
def run_rm_old_background():
  Command().handle()
