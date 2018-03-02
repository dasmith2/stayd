import time

from pays.models import PayableEmail
from pays.management.commands.util import PaypalPayoutCommand


class Command(PaypalPayoutCommand):
  help = 'Send US$1 to the specified email using Paypal'

  def add_arguments(self, parser):
    parser.add_argument('email')

  def handle(self, *args, **options):
    email = options['email']
    payout = PayableEmail.send_test_dollar_via_paypal_to_email(
        options['email'])
    self.stdout.write(self.style.SUCCESS(
        'Sent US$1 to {}. Checking status...'.format(email)))
    self.write_payout_status(payout.check_status())
    while payout.batch_status in ('PROCESSING', 'PENDING'):
      time.sleep(1)
      self.write_payout_status(payout.check_status())
