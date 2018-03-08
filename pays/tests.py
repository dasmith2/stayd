"""
Tests for pays.
"""

from djmoney.money import Money
from django.test import TestCase

import json

from pays.models import Payable, PaypalPayout
from pays.paypal_api import PaypalAPI


class MockPaypalApi(PaypalAPI):
  """
  OK look, I know you're not supposed to make RPC calls in your tests. But
  sending a payment is fast, and this api can get tricky, so I like the idea
  of leaving the send in the actual api. But then it takes a long time, like
  10 seconds or so, for the status to update on the actual API so we really
  do need to mock get_status.
  """
  def get_status(self, payout_batch_id):
    return json.loads("""
{"batch_header": {"amount": {"currency": "USD", "value": "1.0"},
  "batch_status": "SUCCESS",
  "fees": {"currency": "USD", "value": "0.25"},
  "payout_batch_id": "SWZCNHCAR7ST8",
  "sender_batch_header": {"email_subject": "You just got paid by Stayd",
   "sender_batch_id": "5"},
  "time_completed": "2018-02-28T17:10:37Z",
  "time_created": "2018-02-28T17:10:21Z"},
 "items": [{"errors": {"details": [],
    "information_link":
    "https://developer.paypal.com/docs/api/payments.payouts-batch/#errors",
    "message":"This receiver is not registered.",
    "name": "RECEIVER_UNREGISTERED"},
   "links": [{"encType": "application/json",
     "href":
     "https://api.sandbox.paypal.com/v1/payments/payouts-item/5NWWQ5Z6EUQ",
     "method": "GET",
     "rel": "item"}],
   "payout_batch_id": "SWZCNHCAR7ST8",
   "payout_item": {"amount": {"currency": "USD", "value": "1.0"},
    "note": "This is a note on an individual payment",
    "receiver": "dasmith2@gmail.com",
    "recipient_type": "EMAIL",
    "sender_item_id": "5"},
   "payout_item_fee": {"currency": "USD", "value": "0.25"},
   "payout_item_id": "5NWBQWQ5Z6EUQ",
   "time_processed": "2018-02-28T17:10:34Z",
   "transaction_id": "21846482A3831715D",
   "transaction_status": "UNCLAIMED"}],
 "links": [{"encType": "application/json",
   "href":
   "https://api.paypal.com/v1/payments/payouts/SR7ST8?page_size=10&page=1",
   "method": "GET",
   "rel": "self"}]}
     """)


class PaypalPayoutTests(TestCase):
  def get_a_test_payout(self):
    payable = Payable.objects.create(email='does_not_exist_t81nx9j3@gmail.com')
    payout = PaypalPayout.init_new_payout(
        payable,
        Money(1, 'USD'),
        'test_email@gmail.com',
        'Test email subject',
        'Test note')
    payout.paypal_api = MockPaypalApi()
    return payout

  def test_send(self):
    payout = self.get_a_test_payout()

    # This runs against the Paypal sandbox.
    payout.send()

    self.assertTrue(payout.payout_batch_id)
    self.assertEqual(0, payout.sender_batch_id.index('{}-'.format(payout.pk)))
    self.assertEqual(0, payout.sender_item_id.index('{}-'.format(payout.pk)))
    self.assertEqual(payout.email, 'test_email@gmail.com')
    self.assertEqual(payout.email_subject, 'Test email subject')
    self.assertEqual(payout.note, 'Test note')
    self.assertEqual(payout.batch_status, 'PENDING')

  def test_check_status(self):
    payout = self.get_a_test_payout()

    # This runs against a mocked Paypal API.
    payout.check_status()
    payout = PaypalPayout.objects.get(pk=payout.pk)

    self.assertEqual(payout.batch_status, 'SUCCESS')
    # If this fails, they changed the fees.
    self.assertEqual(payout.fee, Money(.25, 'USD'))

    self.assertEqual(payout.transaction_status, 'UNCLAIMED')
    self.assertTrue(payout.transaction_id)

    self.assertTrue(payout.payout_item_id)
    self.assertEqual(payout.error_name, 'RECEIVER_UNREGISTERED')
    self.assertEqual(payout.error_message, "This receiver is not registered.")
