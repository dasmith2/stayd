from guest_messages.models.models import SMS, Email
from commands.stayd_command import StaydCommand


class Command(StaydCommand):
  help = (
      'Alert us about messages that are way overdue and now must be '
      'handled manually.')

  def run(self, verbose):
    SMS.objects.notify_overdue_messages(verbose=verbose)
    Email.objects.notify_overdue_messages(verbose=verbose)

  def name(self):
    return 'alert_overdue_messages'
