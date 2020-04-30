from datetime import date, datetime
from random import randint
from unittest.mock import Mock, call

from django.utils.timezone import make_aware
from djmoney.money import Money

from bento.api import API
from bento.api_examples import (
    TRANSACTION, LOAD_TRANSACTION, TAGGED_TRANSACTION, TRANSACTION_DETAIL)
from bento.models import (
    Transaction, Tag, Card, MerchantCategory, CREDIT, LOAD, COMPLETE)
from expenses.models import DAYS_OF_THE_MONTH, Expense
from rentals.tests import get_test_building
from util.tests import TestCase
from util.timezone import str_to_tz_dt


def get_test_merchant_category(**kwargs):
  return MerchantCategory.objects.create(
      bento_id=kwargs.get('bento_id', randint(0, 1000000)),
      name=kwargs.get('name', 'Whatever.'))


def get_test_card(**kwargs):
  return Card.objects.create(
      card_id=kwargs.get('card_id', 189581),
      alias=kwargs.get('alias', 'McKays card'),
      building=kwargs.get('building', None))


def get_test_transaction(**kwargs):
  if 'tag' in kwargs:
    raise Exception('tag is no longer valid here. Now its tags.')
  transaction = Transaction(
      transaction_id=kwargs.get('transaction_id', randint(0, 1000000)),
      card=kwargs.get('card', None),
      amount=kwargs.get('amount', Money('-47', 'USD')),
      transaction_date=kwargs.get(
          'transaction_date', str_to_tz_dt('2018-05-05 00:00')),
      settlement_date=kwargs.get(
          'settlement_date', str_to_tz_dt('2018-05-06 00:00')),
      payee=kwargs.get('payee', 'Amazon'),
      building=kwargs.get('building', None),
      ttype=kwargs.get('ttype', 'CREDIT'),
      status=kwargs.get('status', 'COMPLETE'),
      deleted=kwargs.get('deleted', False),
      expense=kwargs.get('expense', None))
  transaction.save()
  for tag in kwargs.get('tags', []):
    transaction.tags.add(tag)
  return transaction


class BentoTests(TestCase):
  def test_sync_to_expense(self):
    building = get_test_building()
    card = get_test_card()
    transaction = get_test_transaction(
        settlement_date=str_to_tz_dt('2018-06-07 00:00'),
        amount=Money('-52', 'USD'),
        building=building,
        payee='D&A Electric',
        card=card)

    # Expenses are made automatically on transaction post_save
    self.assertEqual(1, Expense.objects.count())
    transaction.refresh_from_db()
    expense = transaction.expense

    self.assertEqual(date(2018, 6, 1), expense.month)
    self.assertEqual(Money('52', 'USD'), expense.amount)
    self.assertEqual(DAYS_OF_THE_MONTH, expense.amortize)
    self.assertEqual(building, expense.building)
    self.assertEqual(None, expense.owner)
    self.assertEqual('D&A Electric', expense.description)

  def test_sync_transactions(self):
    api = Mock(spec=API)
    api.list_transactions.return_value = [TRANSACTION, LOAD_TRANSACTION]

    # The merchant category for the LOAD_TRANSACTION exists, but not for
    # TRANSACTION.
    get_test_merchant_category(bento_id=-3, name='Whatever')
    api.get_transaction.return_value = TRANSACTION_DETAIL

    for i in range(2):
      Transaction.objects.sync_transactions(
          from_date=date(2018, 5, 1), to_date=date(2018, 5, 3), api=api)
    self.assertEqual(
        2 * [call(date_start=date(2018, 5, 1), date_end=date(2018, 5, 3))],
        api.list_transactions.call_args_list)
    self.assertEqual(2, Transaction.objects.count())
    self.assertEqual(1, Card.objects.count())

    transaction = Transaction.objects.get(ttype=CREDIT)
    self.assertEqual(3653671, transaction.transaction_id)
    card = Card.objects.first()
    self.assertEqual(282308, card.card_id)
    self.assertEqual('1471 Girard BLDG', card.alias)
    self.assertEqual(Money('-7.0', 'USD'), transaction.amount)
    self.assertEqual(
        make_aware(datetime(2018, 10, 9, 18, 12, 49)),
        transaction.transaction_date)
    self.assertEqual(
        make_aware(datetime(2018, 10, 10, 17, 30, 55)),
        transaction.settlement_date)
    self.assertEqual('CRAIGSLIST.ORG', transaction.payee)
    self.assertEqual(CREDIT, transaction.ttype)
    self.assertEqual(COMPLETE, transaction.status)
    self.assertEqual(False, transaction.deleted)
    self.assertEqual('Business Services', transaction.merchant_category.name)
    self.assertEqual(7, transaction.merchant_category.bento_id)

    load_transaction = Transaction.objects.get(ttype=LOAD)
    self.assertIsNone(load_transaction.card)

  def test_sync_transaction_card_with_building(self):
    building = get_test_building()
    get_test_card(
        card_id=282308, alias='1471 Girard BLDG', building=building)
    get_test_merchant_category(bento_id=7, name='Whatever')
    transaction = Transaction.objects.sync_transaction(TRANSACTION)
    self.assertEqual(building, transaction.building)
    self.assertEqual(0, transaction.tags.count())

  def test_create_tag_to_building(self):
    transaction = Transaction.objects.sync_transaction(TAGGED_TRANSACTION)
    # Add an extraneous...
    transaction.tags.add(Tag.objects.create(name='Unrelated'))
    # Resync... then the extra one should go away.
    transaction = Transaction.objects.sync_transaction(TAGGED_TRANSACTION)
    building = get_test_building()

    self.assertEqual(2, transaction.tags.count())
    transaction.tags.get(name='D.C. units')
    girard_tag = transaction.tags.get(name='1471-Girard-St')
    self.assertIsNone(transaction.building)
    girard_tag.building = building
    girard_tag.save()
    transaction.refresh_from_db()

    self.assertEqual(building, transaction.building)

  def test_existing_tag_to_building(self):
    building = get_test_building()
    Tag.objects.create(name='1471-Girard-St', building=building)
    transaction = Transaction.objects.sync_transaction(TAGGED_TRANSACTION)
    self.assertEqual(building, transaction.building)
