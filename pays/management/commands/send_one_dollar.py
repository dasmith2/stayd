import time

from django.core.management.base import BaseCommand

from pays.models import PayableEmail


class Command(BaseCommand):
  help = 'Send US$1 to the specified email using Paypal'

  def add_arguments(self, parser):
    parser.add_argument('email')

  def write_payout_status(self, payout):
    status = payout.batch_status
    if status in ('PROCESSING', 'PENDING'):
      message = self.style.HTTP_INFO(payout.batch_status)
    elif status in ('SUCCESS'):
      message = self.style.SUCCESS(payout.batch_status)
    else:
      message = self.style.WARNING(payout.batch_status)
    self.stdout.write(message)

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
