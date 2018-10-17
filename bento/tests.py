from datetime import date, datetime
from unittest.mock import Mock, call

from django.utils.timezone import make_aware
from djmoney.money import Money

from bento.api import API
from bento.api_examples import (
    TRANSACTION, LOAD_TRANSACTION, TAGGED_TRANSACTION)
from bento.models import (
    Transaction, Card, TagToBuilding, CREDIT, LOAD, COMPLETE)
from rentals.tests import get_test_building
from util.tests import TestCase


class BentoTests(TestCase):
  def test_sync_transactions(self):
    api = Mock(spec=API)
    api.list_transactions.return_value = [TRANSACTION, LOAD_TRANSACTION]
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
    self.assertEqual('', transaction.tag)
    self.assertEqual('Business Services', transaction.category)
    self.assertEqual(CREDIT, transaction.ttype)
    self.assertEqual(COMPLETE, transaction.status)
    self.assertEqual(False, transaction.deleted)

    load_transaction = Transaction.objects.get(ttype=LOAD)
    self.assertIsNone(load_transaction.card)

  def test_create_tag_to_building(self):
    transaction = Transaction.objects.sync_transaction(TAGGED_TRANSACTION)
    building = get_test_building(True)

    self.assertEqual('1471-Girard-St', transaction.tag)
    self.assertIsNone(transaction.building)

    TagToBuilding.objects.create(tag='1471-Girard-St', building=building)
    transaction.refresh_from_db()

    self.assertEqual(building, transaction.building)

  def test_existing_tag_to_building(self):
    building = get_test_building(True)
    TagToBuilding.objects.create(tag='1471-Girard-St', building=building)
    transaction = Transaction.objects.sync_transaction(TAGGED_TRANSACTION)
    self.assertEqual(building, transaction.building)
