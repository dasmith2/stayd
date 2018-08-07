from guest_messages.models import SMS, Email
from guesty.api import GuestySync
from commands.stayd_command import StaydCommand


class Command(StaydCommand):
  help = 'Find all the guest messages that need sending and send them.'

  def run(self, verbose):
    SMS.objects.send(GuestySync(), verbose=verbose)
    SMS.objects.verify_delivery(verbose=verbose)
    Email.objects.send(GuestySync(), verbose=verbose)

  def name(self):
    return 'send_guest_messages'
