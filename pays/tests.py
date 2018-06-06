"""
Tests for pays.
"""
from datetime import date

from djmoney.money import Money
from django.test import TestCase

from pays.models import Payable, PaypalPayout
from pays.paypal_api import MockPaypalApi


class PaypalPayoutTests(TestCase):
  def get_a_test_payout(self):
    payable = Payable.objects.create(email='does_not_exist_t81nx9j3@gmail.com')
    payout = PaypalPayout.init_new_payout(
        who_to_pay=payable,
        amount=Money(1, 'USD'),
        email_subject='Test email subject',
        note='Test note',
        when_should=date.today())
    payout.paypal_api = MockPaypalApi()
    return payout

  def test_weird_response(self):
    payout = self.get_a_test_payout()
    payout.paypal_api.custom_response = {'hello': 'world!'}
    payout.send()
    self.assertEqual('API_ERROR', payout.error_name)
    self.assertEqual("{'hello': 'world!'}", payout.error_message)

  def test_insufficient_funds(self):
    payout = self.get_a_test_payout()
    payout.paypal_api.insufficient_funds = True
    payout.send()
    self.assertEqual('INSUFFICIENT_FUNDS', payout.error_name)

  def test_send(self):
    payout = self.get_a_test_payout()

    payout.send()

    self.assertTrue(payout.payout_batch_id)
    self.assertTrue(payout.public_id)
    self.assertEqual(
        payout.who_to_pay.email, 'does_not_exist_t81nx9j3@gmail.com')
    self.assertEqual(payout.email_subject, 'Test email subject')
    self.assertEqual(payout.note, 'Test note')
    self.assertEqual(payout.batch_status, 'PENDING')

  def test_check_status(self):
    payout = self.get_a_test_payout()
    self.assertIsNone(payout.when_did)

    # This runs against a mocked Paypal API.
    payout.check_status()
    payout = PaypalPayout.objects.get(pk=payout.pk)

    self.assertEqual(payout.batch_status, 'SUCCESS')
    self.assertEqual(payout.paypal_fee, Money(.25, 'USD'))

    self.assertEqual(payout.transaction_status, 'UNCLAIMED')
    self.assertTrue(payout.transaction_id)
    self.assertIsNotNone(payout.when_did)

    self.assertTrue(payout.payout_item_id)
    self.assertEqual(payout.error_name, 'RECEIVER_UNREGISTERED')
    self.assertEqual(payout.error_message, "This receiver is not registered.")
