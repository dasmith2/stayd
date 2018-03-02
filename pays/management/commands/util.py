from django.core.management.base import BaseCommand

class PaypalPayoutCommand(BaseCommand):
  def write_payout_status(self, payout):
    status = payout.batch_status
    message = '{} to {} on {}: {}'.format(
        payout.amount, payout.email, payout.when, status)
    if status in ('PROCESSING', 'PENDING'):
      message = self.style.HTTP_INFO(message)
    elif status in ('SUCCESS'):
      message = self.style.SUCCESS(message)
    else:
      message = self.style.WARNING(message)
    self.stdout.write(message)
