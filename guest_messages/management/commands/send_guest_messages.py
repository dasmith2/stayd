from guest_messages.models.sms import SMS
from guest_messages.models.email import Email
from commands.stayd_command import StaydCommand
from util.background import background
from util.html_status_codes import ServerError


class Command(StaydCommand):
  """
  This runs in two places at the moment. First it runs on the hour as part of
  clock.py But I also kick it off hourly in heroku addons:open scheduler -a
  stayd-prod as a backup. I added that when, one time, Redis ran out of memory
  and all background tasks halted until I could figure it out.
  """
  help = 'Find all the guest messages that need sending and send them.'

  def run(self, verbose):
    SMS.objects.send(verbose=verbose)
    try:
      SMS.objects.verify_delivery(verbose=verbose)
    except ServerError:
      pass  # NBD, just let it try again in an hour.
    Email.objects.send(verbose=verbose)

    SMS.objects.notify_overdue_messages(verbose=verbose)
    Email.objects.notify_overdue_messages(verbose=verbose)

  def name(self):
    return 'send_guest_messages'


@background
def run_send_guest_messages_background():
  Command().handle()
