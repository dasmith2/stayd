from guest_messages.models import SMS
from commands.stayd_command import StaydCommand


class Command(StaydCommand):
  help = (
      'Alert us about messages that are way overdue and now must be '
      'handled manually.')

  def run(self, verbose):
    SMS.objects.notify_overdue_messages(verbose=verbose)

  def name(self):
    return 'alert_overdue_messages'
