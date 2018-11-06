from unittest.mock import Mock

from djmoney.money import Money

from stripe.api import API
from stripe.api_examples import PAYOUTS
from stripe.models import Payout
from util.tests import TestCase
from util.timezone import ts_to_utc_dt


class PayoutTests(TestCase):
  def test_sync_payouts(self):
    api = Mock(spec=API)
    api.get_payouts.return_value = PAYOUTS['data']
    Payout.objects.sync_payouts(api=api)
    self.assertEqual(2, Payout.objects.count())
    payout1 = Payout.objects.first()
    self.assertEqual('po_1DRW4qCeiXlAlNN1xdw7tWmP', payout1.payout_id)
    self.assertEqual(Money('-.10', 'USD'), payout1.amount)
    self.assertEqual(ts_to_utc_dt(1541116800), payout1.arrival_date)
