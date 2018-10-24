from guest_messages.models.models import SMS, Email
from commands.stayd_command import StaydCommand
from util.background import background


class Command(StaydCommand):
  help = 'Find all the guest messages that need sending and send them.'

  def run(self, verbose):
    SMS.objects.send(verbose=verbose)
    SMS.objects.verify_delivery(verbose=verbose)
    Email.objects.send(verbose=verbose)

    SMS.objects.notify_overdue_messages(verbose=verbose)
    Email.objects.notify_overdue_messages(verbose=verbose)

  def name(self):
    return 'send_guest_messages'


@background
def run_send_guest_messages_background():
  Command().handle()
