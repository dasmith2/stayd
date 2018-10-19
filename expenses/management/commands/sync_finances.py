from datetime import date, timedelta

from bento.models import Transaction as BentoTransaction
from commands.stayd_command import StaydCommand
from xxero.models import Transaction as XeroTransaction


class Command(StaydCommand):
  def run(self, verbose):
    from_date = date.today() - timedelta(days=3)
    to_date = date.today()
    BentoTransaction.objects.sync_transactions(from_date, to_date)
    XeroTransaction.objects.sync_transactions(from_date, to_date)

  def name(self):
    return 'sync_finances'
