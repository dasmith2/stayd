""" Bento is totally dead. """
from datetime import date, timedelta
import pprint

from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.shortcuts import reverse
from django.utils.timezone import make_aware
from djmoney.models.fields import MoneyField
from djmoney.money import Money

from bento.api import API
from errors.models import log_error, notify
from expenses.models import Expense
from rentals.models import Building
from util.background import background
from util.signals import post_sync


class CardManager(models.Manager):
  def sync_card(self, card_data):
    card_id = card_data['cardId']
    card = self.filter(card_id=card_id).first()
    if not card:
      card = Card(card_id=card_id)
    alias = card_data['alias']
    if card.alias != alias:
      card.alias = alias
      notify_new_card = not card.pk
      card.save()
      if notify_new_card:
        self.notify_new_card(card)
    return card

  def notify_new_card(self, card):
    url = settings.KEYS_SERVER + reverse(
        'admin:bento_card_change', args=(card.pk,))
    notify(
        settings.ALERT_NEW_BENTO_CARD_OR_TAG,
        'New Bento card encoutered', (
            'If this is a building card, please set the "Building" '
            'property at {}'.format(url)))


class Card(models.Model):
  card_id = models.PositiveIntegerField(unique=True, help_text=(
      'This comes from bento'))
  alias = models.CharField(max_length=200)
  building = models.ForeignKey(
      Building, on_delete=models.CASCADE, null=True, blank=True)

  objects = CardManager()

  class Meta:
    ordering = ('alias',)

  def __str__(self):
    return self.alias

  def __repr__(self):
    if self.building:
      return '<Card({}, {})>'.format(self.alias, self.building.nickname)
    return '<Card({}, No building)>'.format(self.alias)


COMPLETE = 'COMPLETE'
PENDING = 'PENDING'
DECLINED = 'DECLINED'
TRANSACTION_STATUS_CHOICES = (
    (COMPLETE, COMPLETE),
    (PENDING, PENDING))


CREDIT = 'CREDIT'
LOAD = 'LOAD'
REFUND = 'REFUND'
FEE = 'FEE'
TRANSACTION_TYPE_CHOICES = (
    (CREDIT, CREDIT),
    (LOAD, LOAD),
    (REFUND, REFUND),
    (FEE, FEE))


class TagManager(models.Manager):
  def sync_tag(self, name):
    tag_obj, created = self.get_or_create(name=name)
    if created:
      self.notify_new_tag(tag_obj)
    return tag_obj

  def notify_new_tag(self, tag):
    url = settings.KEYS_SERVER + reverse(
        'admin:bento_tag_change', args=(tag.pk,))
    notify(
        settings.ALERT_NEW_BENTO_CARD_OR_TAG,
        'New Bento tag encoutered', (
            'If this is a building tag, please set the "Building" '
            'property at {}'.format(url)))


class Tag(models.Model):
  name = models.CharField(max_length=200, primary_key=True)
  building = models.ForeignKey(
      Building, on_delete=models.CASCADE, null=True, blank=True)

  objects = TagManager()


class TransactionManager(models.Manager):
  def sync_to_expenses(self):
    for transaction in self.filter(
        expense__isnull=True, building__isnull=False):
      transaction.sync_to_expense()

  def _get_merchant_category(self, transaction_data, api=None):
    # The issue is that transactions in a list are, like, 'category':
    # {'transactionCategoryId': 11} while transaction details are, like,
    # 'category': {transactionCategoryId': 11, 'name': 'Retail and
    # Miscellaneous Stores', ...}. Also there's no way to retrieve categories
    # separate from transactions. So if we encounter a new category we gotta
    # load the transaction.
    api = api or API()
    category_data = transaction_data.get('category', {})
    merchant_category_id = category_data.get('transactionCategoryId', None)
    if not merchant_category_id:
      return None
    existing = MerchantCategory.objects.filter(
        bento_id=merchant_category_id).first()
    if existing:
      return existing
    name = category_data.get('name', None)
    if not name:
      transaction_data = api.get_transaction(
          transaction_data['cardTransactionId'])
      category = transaction_data['category']
      if 'name' in category:
        name = category['name']
      else:
        # don't json.dumps(transaction_data, indent=2) because Object of type
        # 'datetime' is not JSON serializable
        raise Exception(
            'Unable to get merchant category name from {}', transaction_data)
    return MerchantCategory.objects.create(
        bento_id=merchant_category_id, name=name)

  def sync_transaction(self, transaction_data, api=None, verbose=False):
    transaction_id = transaction_data['cardTransactionId']
    status = transaction_data['status']
    if status == DECLINED:
      if verbose:
        print(transaction_id, DECLINED)
      return
    transaction_date = transaction_data['transactionDate']
    amount = transaction_data['amount']
    payee = transaction_data['payee']['name']

    if verbose:
      print(transaction_id, transaction_date, amount, payee)

    transaction = self.filter(transaction_id=transaction_id).first()
    if not transaction:
      transaction = Transaction(transaction_id=transaction_id)

    card = transaction_data.get('card', None)
    if card:
      transaction.card = Card.objects.sync_card(transaction_data['card'])
      if transaction.card.building:
        transaction.building = transaction.card.building
    # In the case of CREDIT and FEE transactions, Bento sends along a negative
    # number. In the case of REFUND and LOAD transactions, Bento sends a
    # positive number.
    transaction.amount = Money(str(amount), transaction_data['currency'])
    transaction.transaction_date = make_aware(transaction_date)
    transaction.settlement_date = make_aware(
        transaction_data['settlementDate'])
    transaction.payee = payee
    building_must_match = transaction.building and transaction.card and (
        transaction.card.building)
    if building_must_match and (
        transaction.building != transaction.card.building):
      log_error(
          'Not sure what building for this transaction',
          '{} != {} in transaction {}'.format(
              transaction.building, transaction.card.building, transaction.pk))
    transaction.ttype = transaction_data['type']
    transaction.status = status
    transaction.deleted = transaction_data['deleted']
    transaction.merchant_category = self._get_merchant_category(
        transaction_data, api)
    transaction.save()

    self._sync_tags(transaction_data, transaction)

    if any([
        transaction.deleted,
        transaction.status not in [COMPLETE, PENDING],
        transaction.ttype not in [CREDIT, LOAD, FEE, REFUND]]):
      pretty_data = pprint.PrettyPrinter(indent=2).pformat(transaction_data)
      log_error(
          'Got a weird Bento transaction',
          'pk {}\n\n{}'.format(transaction.pk, pretty_data))

    return transaction

  def _sync_tags(self, transaction_data, transaction):
    tags = transaction_data['tags']
    if tags:
      # Sometimes they come in with more than one tag even though usually one
      # of the tags is useless.
      tag_objs = []
      for tag in tags:
        tag_obj = Tag.objects.sync_tag(tag['name'])
        if tag_obj.building:
          transaction.building = tag_obj.building
        tag_objs.append(tag_obj)
      transaction.tags.set(tag_objs)

  def sync_transactions(self, from_date, to_date, api=API(), verbose=False):
    for transaction_data in api.list_transactions(
        date_start=from_date, date_end=to_date):
      self.sync_transaction(transaction_data, api, verbose)


@background
def sync_transactions_background(days_ago=14):
  from_date = date.today() - timedelta(days=days_ago)
  to_date = None
  Transaction.objects.sync_transactions(from_date, to_date)


class MerchantCategory(models.Model):
  bento_id = models.IntegerField(
      primary_key=True, help_text='Negative ids exist.')
  name = models.CharField(max_length=200)

  class Meta:
    ordering = ('name',)

  def __repr__(self):
    return '<MerchantCategory {}: {}>'.format(self.pk, self.name)


class Transaction(models.Model):
  transaction_id = models.PositiveIntegerField(
      help_text='This comes from Bento', unique=True)
  card = models.ForeignKey(
      Card, on_delete=models.CASCADE, null=True, blank=True, help_text=(
          'LOAD transactions have no card.'))
  amount = MoneyField(
      max_digits=10, decimal_places=2, default_currency='USD', help_text=(
          'Looks like this is typically negative'))
  transaction_date = models.DateTimeField()
  settlement_date = models.DateTimeField()
  payee = models.CharField(max_length=200)
  tags = models.ManyToManyField(Tag)
  building = models.ForeignKey(
      Building, on_delete=models.CASCADE, null=True, blank=True, help_text=(
          'This is based on tags.'))
  ttype = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES)
  status = models.CharField(max_length=20, choices=TRANSACTION_STATUS_CHOICES)
  deleted = models.BooleanField()
  expense = models.ForeignKey(
      Expense, on_delete=models.CASCADE, null=True, blank=True, help_text=(
          'The expense that is calculated directly from this transaction.'))
  merchant_category = models.ForeignKey(
      MerchantCategory, on_delete=models.PROTECT, null=True, blank=True)

  objects = TransactionManager()

  # I wish I could write def admin_url(self): but I'm afraid Bento doesn't have
  # a page for viewing a single transaction. You'll have to go to
  # https://app.bentoforbusiness.com/15841/transactions and dig around for it.

  def sync_to_expense(self):
    if self.building:
      expense = self.expense
      if not expense:
        expense = Expense()
      month = date(
          self.settlement_date.year, self.settlement_date.month, 1)
      # CREDITs come from Bento negative, REFUNDS come from Bento positive.
      # Expense treats them the other way around.
      amount = -self.amount

      if any([
          expense.month != month,
          expense.amount != amount,
          expense.building != self.building,
          expense.description != self.payee]):
        expense.month = month
        expense.amount = amount
        expense.building = self.building
        expense.owner = None
        expense.description = self.payee
        expense.save()
        self.expense = expense
        self.save()
        post_sync.send(sender=Expense, instance=expense)
    return expense

  class Meta:
    ordering = ('-transaction_date',)

  def __repr__(self):
    return '<(Bento)Transaction {}: {} {}>'.format(
        self.pk, self.transaction_date, self.amount)


@receiver(post_save, sender=Tag)
def tag_to_building_post_save(sender, instance, *args, **kwargs):
  Transaction.objects.filter(tags=instance).update(
      building=instance.building)


@receiver(post_save, sender=Card)
def card_post_save(sender, instance, *args, **kwargs):
  Transaction.objects.filter(card=instance).update(building=instance.building)


@receiver(post_save, sender=Transaction)
def transaction_post_save(sender, instance, *args, **kwargs):
  if instance.building:
    if not instance.expense:
      instance.sync_to_expense()
