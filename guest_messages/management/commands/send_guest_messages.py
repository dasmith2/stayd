from guest_messages.models import Message
from guesty.api import GuestySync
from commands.stayd_command import StaydCommand


class Command(StaydCommand):
  help = 'Find all the guest messages that need sending and send them.'

  def run(self, verbose):
    Message.objects.send(GuestySync(), verbose=verbose)
    Message.objects.verify_delivery(verbose=verbose)

  def name(self):
    return 'send_guest_messages'
