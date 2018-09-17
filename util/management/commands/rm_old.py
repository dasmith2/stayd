"""
See also util/rm_old.py
"""
from commands.stayd_command import StaydCommand
from guest_messages.models.models import RawMandrillEvent
from guesty.models import RawEvent
from performance.models import LongRequest


class Command(StaydCommand):
  help = (
      'RawEvents are created when a Guesty webhook runs. They build up '
      'over time so they have to be cleaned up. The command removes '
      'any that are older than 31 days.')

  def run(self, verbose):
    # One time I needed some of these that were 45 days old, so, they were
    # gone because the default is 31.
    RawEvent.objects.rm_old(days_ago=60, verbose=verbose)
    RawMandrillEvent.objects.rm_old(verbose=verbose)
    LongRequest.objects.rm_old(verbose=verbose)

  def name(self):
    return 'rm_old_events'
