from datetime import date, datetime
from decimal import Decimal
from unittest.mock import Mock, call
from uuid import UUID, uuid4 as random_uuid

from django.utils.timezone import make_aware
from djmoney.money import Money

from util.timezone import str_to_tz_dt
from xxero.api import API
from xxero.api_examples import (
    SPEND_TRANSACTION, RECEIVE_TRANSACTION, LIST_RECEIVE_TRANSFER_TRANSACTION,
    RECEIVE_TRANSFER_TRANSACTION, REGULAR_ACCOUNT,
    TRANSACTION_WITH_LINE_ITEMS)
from xxero.models.coconuts import BankAccount, Coconut
from xxero.models.contacts import Contact
from xxero.models.transactions import (
    Transaction, LineItem, SPEND, RECEIVE, AUTHORISED)
from xxero.tests.test_businesses import get_test_business
from xxero.tests.test_coconuts import get_test_coconut, get_test_bank_account
from xxero.tests.test_contacts import get_test_contact


def get_test_transaction(**kwargs):
  contact = kwargs.get('contact', None)
  if not contact:
    contact = get_test_contact(**kwargs)
  bank_account = kwargs.get('bank_account', None)
  if not bank_account:
    bank_account = get_test_bank_account(**kwargs)
  return Transaction.objects.create(
      bank_transaction_id=kwargs.get('bank_transaction_id', random_uuid()),
      bank_account=kwargs.get('bank_account', bank_account),
      transfer_bank=kwargs.get('transfer_bank', None),
      xero_type=kwargs.get('xero_type', SPEND),
      contact=kwargs.get('contact', contact),
      when=kwargs.get('when', str_to_tz_dt('2019-02-01')),
      amount=kwargs.get('amount', Money('888.99', 'USD')),
      status=kwargs.get('status', AUTHORISED),
      status_check_at=kwargs.get('status_check_at', None),
      reference=kwargs.get('reference', None))


def get_test_line_item(**kwargs):
  transaction = kwargs.get('transaction', None)
  if not transaction:
    transaction = get_test_transaction(**kwargs)
  coconut = kwargs.get('coconut', None)
  if not coconut:
    coconut = get_test_coconut(**kwargs)
  line_item = LineItem.objects.create(
      transaction=transaction,
      line_item_id=kwargs.get('line_item_id', random_uuid()),
      amount=kwargs.get('amount', Money('999.44', 'USD')),
      coconut=kwargs.get('coconut', coconut))
  line_item.tracking_options.set(kwargs.get('tracking_options', []))
  return line_item


class TransactionTests(object):
  def test_sync_line_items(self):
    api = Mock(spec=API)
    # 171 Accumulated Depreciation - AC Equipment
    api.account_by_code.return_value = REGULAR_ACCOUNT
    stuff = get_test_coconut(code='460', name='Stuff & stuff')
    things = get_test_coconut(code='605', name='Things?')
    rock_and_roll = get_test_coconut(code='2200', name='Rock & roll baby')
    business = get_test_business()
    for i in range(2):
      # This has line items with coconut codes 171, 460, 605, 2200
      Transaction.objects.sync_transaction(
          TRANSACTION_WITH_LINE_ITEMS, business, api=api)
    transaction = Transaction.objects.first()
    self.assertEqual(5, LineItem.objects.count())
    self.assertEqual(5, transaction.lineitem_set.count())
    self.assertEqual(4, Coconut.objects.count())
    li1 = transaction.lineitem_set.get(
        line_item_id=UUID('9522c7bd-d9fb-46db-9220-347c297d52a7'),
        amount=Money('1796.7', 'USD'),
        coconut__code='171')
    transaction.lineitem_set.get(
        line_item_id=UUID('f366a684-fc6e-4f7b-861a-48c14902ef31'),
        amount=Money('230.0', 'USD'),
        coconut=stuff)
    transaction.lineitem_set.get(
        line_item_id=UUID('49754ca1-aad5-4629-9732-8c436032fe91'),
        amount=Money('-60.8', 'USD'),
        coconut=things)
    transaction.lineitem_set.get(
        line_item_id=UUID('d295f0da-3960-4e59-8119-dc77c9ba2308'),
        amount=Money('-305.45', 'USD'),
        coconut=rock_and_roll)
    transaction.lineitem_set.get(
        line_item_id=UUID('977f694c-b3de-428e-9a85-5bcc71597e4c'),
        amount=Money('-180.96', 'USD'),
        coconut=rock_and_roll)

    self.assertEqual(2, li1.tracking_options.count())
    tci1 = UUID('cf510f12-341c-4187-afc4-47aab451fc71')
    li1.tracking_options.get(
        tracking_category__tracking_category_id=tci1,
        tracking_category__name='Card',
        tracking_option_id=UUID('158b715a-3463-432e-adca-abcf061ef43e'),
        name='243 Montgomery BLDG')
    tci2 = UUID('e2b3849d-dbe6-43d8-91ae-a1baa6b09902')
    li1.tracking_options.get(
        tracking_category__tracking_category_id=tci2,
        tracking_category__name='Building',
        tracking_option_id=UUID('f9b54796-b921-4fd4-97b3-23f8cb5a5bf0'),
        name='243 Montgomery Street, Jersey City')

    get_test_line_item(transaction=transaction)
    self.assertEqual(6, transaction.lineitem_set.count())
    Transaction.objects.sync_transaction(
        TRANSACTION_WITH_LINE_ITEMS, business, api=api)
    self.assertEqual(5, transaction.lineitem_set.count())

  def test_sync_transactions(self):
    api = Mock(spec=API)
    api.bank_transactions.return_value = [
        SPEND_TRANSACTION, RECEIVE_TRANSACTION]

    def bank_transaction(bank_transaction_id):
      if bank_transaction_id == 'd3326e7d-7e55-4775-8287-8c2d65ff5cc3':
        return SPEND_TRANSACTION
      if bank_transaction_id == '7dc4eff5-d1e1-4d8f-a244-949351aefb25':
        return RECEIVE_TRANSACTION
      raise Exception(bank_transaction_id)

    api.bank_transaction.side_effect = bank_transaction
    business = get_test_business()
    for i in range(2):
      Transaction.objects.sync_transactions(
          date(2018, 1, 1), business, api=api)
    self.assertEqual(2, BankAccount.objects.count())
    self.assertEqual(2, Contact.objects.count())
    self.assertEqual(2, Transaction.objects.count())
    self.assertEqual(
        [call(date(2018, 1, 1)), call(date(2018, 1, 1))],
        api.bank_transactions.call_args_list)

    spend = Transaction.objects.get(xero_type=SPEND)
    receive = Transaction.objects.get(xero_type=RECEIVE)
    self.assertEqual('9J897174GH868522M', receive.reference)

    self.assertIsNone(spend.reference)
    self.assertEqual(
        UUID('d3326e7d-7e55-4775-8287-8c2d65ff5cc3'),
        spend.bank_transaction_id)
    self.assertEqual(
        UUID('7ba80fd2-a0af-447c-a853-9fb548b194a9'),
        spend.bank_account.account_id)
    self.assertEqual('Chase ExecResidence Housing', spend.bank_account.name)
    self.assertEqual(business, spend.bank_account.business)
    self.assertEqual(
        UUID('539b70bf-2d8b-435c-8adc-0aa67e409a6e'), spend.contact.contact_id)
    self.assertEqual('Black Barn', spend.contact.name)
    self.assertEqual(date(2018, 3, 16), spend.when)
    self.assertEqual(Money(Decimal('132.52'), 'USD'), spend.amount)
    self.assertEqual(
        make_aware(datetime(2018, 3, 28, 19, 45, 13, 293000)),
        spend.updated_at)
    self.assertEqual(AUTHORISED, spend.status)
    self.assertTrue(bool(spend.status_check_at))

  def test_sync_transactions_transfer(self):
    api = Mock(spec=API)
    api.bank_transactions.return_value = [LIST_RECEIVE_TRANSFER_TRANSACTION]
    api.bank_transaction.return_value = RECEIVE_TRANSFER_TRANSACTION
    Transaction.objects.sync_transactions(
        date(2018, 1, 1), get_test_business(), api=api)
    self.assertEqual(
        'Paypal ExecResidence', Transaction.objects.first().transfer_bank.name)

  def test_match_account_ids_to_names(self):
    business = get_test_business()
    transaction = Transaction.objects.sync_transaction(
        RECEIVE_TRANSFER_TRANSACTION, business)
    self.assertEqual('Paypal ExecResidence', transaction.transfer_bank.name)
    self.assertEqual(business, transaction.transfer_bank.business)
    self.assertIsNone(transaction.transfer_bank.account_id)
    Transaction.objects.sync_transaction(
        RECEIVE_TRANSACTION, business)
    transaction.transfer_bank.refresh_from_db()
    self.assertEqual(
        UUID('5200f6d4-6483-4186-8b4d-e4a1a178e496'),
        transaction.transfer_bank.account_id)

  def test_no_need_to_match_account_ids_to_names(self):
    business = get_test_business()
    Transaction.objects.sync_transaction(
        RECEIVE_TRANSACTION, business)
    transaction = Transaction.objects.sync_transaction(
        RECEIVE_TRANSFER_TRANSACTION, business)
    self.assertEqual(
        UUID('5200f6d4-6483-4186-8b4d-e4a1a178e496'),
        transaction.transfer_bank.account_id)
