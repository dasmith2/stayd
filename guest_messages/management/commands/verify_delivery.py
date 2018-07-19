from commands.stayd_command import StaydCommand
from guest_messages.models import Message


class Command(StaydCommand):
  help = 'Find all the guest messages that need sending and send them.'

  def run(self, verbose):
    Message.objects.verify_delivery(verbose=verbose)

  def name(self):
    return 'verify_delivery'
