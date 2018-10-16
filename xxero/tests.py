from datetime import date
from decimal import Decimal
from unittest.mock import Mock, call
from util.tests import TestCase
from uuid import UUID

from djmoney.money import Money

from xxero.api import API
from xxero.api_examples import (
    SPEND_TRANSACTION, RECEIVE_TRANSACTION, LIST_RECEIVE_TRANSFER_TRANSACTION,
    RECEIVE_TRANSFER_TRANSACTION)
from xxero.models import Transaction, BankAccount, Contact, SPEND, RECEIVE


class TransactionTests(TestCase):
  def test_sync_transactions(self):
    api = Mock(spec=API)
    api.bank_transactions.return_value = [
        SPEND_TRANSACTION, RECEIVE_TRANSACTION]
    Transaction.objects.sync_transactions(
        date(2018, 1, 1), date(2018, 1, 3), api=api)
    self.assertEqual(2, BankAccount.objects.count())
    self.assertEqual(2, Contact.objects.count())
    self.assertEqual(2, Transaction.objects.count())
    self.assertEqual(
        [call(date(2018, 1, 1)), call(date(2018, 1, 2))],
        api.bank_transactions.call_args_list)

    spend = Transaction.objects.get(xero_type=SPEND)
    Transaction.objects.get(xero_type=RECEIVE)

    self.assertEqual(
        UUID('d3326e7d-7e55-4775-8287-8c2d65ff5cc3'),
        spend.bank_transaction_id)
    self.assertEqual(
        UUID('7ba80fd2-a0af-447c-a853-9fb548b194a9'),
        spend.bank_account.account_id)
    self.assertEqual('Chase ExecResidence Housing', spend.bank_account.name)
    self.assertEqual(
        UUID('539b70bf-2d8b-435c-8adc-0aa67e409a6e'), spend.contact.contact_id)
    self.assertEqual('Black Barn', spend.contact.name)
    self.assertEqual(date(2018, 3, 16), spend.when)
    self.assertEqual(Money(Decimal('132.52'), 'USD'), spend.amount)

  def test_sync_transactions_transfer(self):
    api = Mock(spec=API)
    api.bank_transactions.return_value = [LIST_RECEIVE_TRANSFER_TRANSACTION]
    api.bank_transaction.return_value = RECEIVE_TRANSFER_TRANSACTION
    Transaction.objects.sync_transactions(
        date(2018, 1, 1), date(2018, 1, 2), api=api)
    self.assertEqual(
        'Paypal ExecResidence', Transaction.objects.first().transfer_bank.name)

  def test_match_account_ids_to_names(self):
    transaction = Transaction.objects.sync_transaction(
        RECEIVE_TRANSFER_TRANSACTION)
    self.assertEqual(
        'Paypal ExecResidence', transaction.transfer_bank.name)
    self.assertIsNone(transaction.transfer_bank.account_id)
    Transaction.objects.sync_transaction(RECEIVE_TRANSACTION)
    transaction.transfer_bank.refresh_from_db()
    self.assertEqual(
        UUID('5200f6d4-6483-4186-8b4d-e4a1a178e496'),
        transaction.transfer_bank.account_id)

  def test_no_need_to_match_account_ids_to_names(self):
    Transaction.objects.sync_transaction(RECEIVE_TRANSACTION)
    transaction = Transaction.objects.sync_transaction(
        RECEIVE_TRANSFER_TRANSACTION)
    self.assertEqual(
        UUID('5200f6d4-6483-4186-8b4d-e4a1a178e496'),
        transaction.transfer_bank.account_id)
