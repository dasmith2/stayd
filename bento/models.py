from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.timezone import make_aware
from djmoney.models.fields import MoneyField
from djmoney.money import Money

from bento.api import API
from errors.models import log_error
from rentals.models import Building


class CardManager(models.Manager):
  def sync_card(self, card_dict):
    card_id = card_dict['cardId']
    card = self.filter(card_id=card_id).first()
    if not card:
      card = Card(card_id=card_id)
    alias = card_dict['alias']
    if card.alias != alias:
      card.alias = alias
      card.save()
    return card


class Card(models.Model):
  card_id = models.PositiveIntegerField()
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
TRANSACTION_TYPE_CHOICES = (
    (CREDIT, CREDIT),
    (LOAD, LOAD),
    (REFUND, REFUND))


class TagToBuilding(models.Model):
  tag = models.CharField(max_length=200)
  building = models.ForeignKey(
      Building, on_delete=models.CASCADE, null=True, blank=True)


@receiver(post_save, sender=TagToBuilding)
def tag_to_building_post_save(sender, instance, *args, **kwargs):
  Transaction.objects.filter(tag=instance.tag).update(
      building=instance.building)


@receiver(post_save, sender=Card)
def card_post_save(sender, instance, *args, **kwargs):
  Transaction.objects.filter(card=instance).update(building=instance.building)


class TransactionManager(models.Manager):
  def sync_transaction(self, transaction_dict, verbose=False):
    transaction_id = transaction_dict['cardTransactionId']
    status = transaction_dict['status']
    if status == DECLINED:
      if verbose:
        print(transaction_id, DECLINED)
      return
    transaction_date = transaction_dict['transactionDate']
    amount = transaction_dict['amount']
    payee = transaction_dict['payee']['name']

    if verbose:
      print(transaction_id, transaction_date, amount, payee)

    transaction = self.filter(transaction_id=transaction_id).first()
    if not transaction:
      transaction = Transaction(transaction_id=transaction_id)

    card = transaction_dict.get('card', None)
    if card:
      transaction.card = Card.objects.sync_card(transaction_dict['card'])
    transaction.amount = Money(str(amount), transaction_dict['currency'])
    transaction.transaction_date = make_aware(transaction_date)
    transaction.settlement_date = make_aware(
        transaction_dict['settlementDate'])
    transaction.payee = payee
    tags = transaction_dict['tags']
    if tags:
      transaction.tag = tags[0]['name']
      if transaction.tag:
        tag_to_building = TagToBuilding.objects.filter(
            tag=transaction.tag).first()
        if tag_to_building:
          if tag_to_building.building:
            transaction.building = tag_to_building.building
        else:
          TagToBuilding.objects.create(tag=transaction.tag)
    transaction.category = transaction_dict['category']['name']
    transaction.ttype = transaction_dict['type']
    transaction.status = status
    transaction.deleted = transaction_dict['deleted']
    transaction.save()
    if any([
        transaction.deleted,
        transaction.status not in [COMPLETE, PENDING],
        transaction.ttype not in [CREDIT, LOAD],
        len(tags) > 1]):
      log_error('Got a weird Bento transaction', str(transaction_dict))

    return transaction

  def sync_transactions(self, from_date, to_date, api=API(), verbose=False):
    for transaction_dict in api.list_transactions(
        date_start=from_date, date_end=to_date):
      self.sync_transaction(transaction_dict, verbose)


class Transaction(models.Model):
  transaction_id = models.PositiveIntegerField()
  card = models.ForeignKey(
      Card, on_delete=models.CASCADE, null=True, blank=True, help_text=(
          'LOAD transactions have no card.'))
  amount = MoneyField(
      max_digits=10, decimal_places=2, default_currency='USD', help_text=(
          'Looks like this is typically negative'))
  transaction_date = models.DateTimeField()
  settlement_date = models.DateTimeField()
  payee = models.CharField(max_length=200)
  tag = models.TextField(default='', blank=True)
  building = models.ForeignKey(
      Building, on_delete=models.CASCADE, null=True, blank=True, help_text=(
          'This is based on tag and TagToBuilding'))
  category = models.CharField(max_length=200)
  ttype = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES)
  status = models.CharField(max_length=20, choices=TRANSACTION_STATUS_CHOICES)
  deleted = models.BooleanField()

  objects = TransactionManager()

  class Meta:
    ordering = ('-transaction_date',)
