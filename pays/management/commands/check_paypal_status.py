from pays.management.commands.util import PaypalPayoutCommand
from pays.models import PaypalPayout

class Command(PaypalPayoutCommand):
  help = 'Check status on all PENDING or PROCESSING Paypal payouts'

  def handle(self, *args, **options):
    for payout in PaypalPayout.objects.filter(
        batch_status__in=('PROCESSING', 'PENDING')):
      self.write_payout_status(payout.check_status())
