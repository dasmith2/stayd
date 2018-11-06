from django.db import models
from djmoney.models.fields import MoneyField
from djmoney.money import Money

from stripe.api import API
from util.timezone import ts_to_utc_dt


class PayoutManager(models.Manager):
  def payout_from_data(self, data):
    return Payout(
        payout_id=data['id'],
        amount=Money(data['amount'] / 100, data['currency'].upper()),
        arrival_date=ts_to_utc_dt(data['arrival_date']))

  def sync_payouts(self, api=API()):
    for payout_data in api.get_payouts():
      payout = self.payout_from_data(payout_data)
      if self.filter(payout_id=payout.payout_id).exists():
        break
      payout.save()


class Payout(models.Model):
  payout_id = models.CharField(max_length=200, db_index=True)
  amount = MoneyField(
      max_digits=10, decimal_places=2, default_currency='USD')
  arrival_date = models.DateTimeField()

  objects = PayoutManager()

  class Meta:
    ordering = ('-arrival_date',)


CHARGE = 'charge'
PAYOUT = 'payout'
TRANSACTION_TYPE_CHOICES = (
    (CHARGE, CHARGE),
    (PAYOUT, PAYOUT))


class BalanceTransaction(models.Model):
  balance_transaction_id = models.CharField(max_length=200, db_index=True)
  payout = models.ForeignKey(Payout, on_delete=models.CASCADE)
  amount = models.DecimalField(max_digits=10, decimal_places=2)
  total_fees = models.DecimalField(max_digits=10, decimal_places=2)
  net = models.DecimalField(max_digits=10, decimal_places=2)
  currency = models.CharField(max_length=3, default='USD')
  ttype = models.CharField(max_length=100, choices=TRANSACTION_TYPE_CHOICES)


class Fee(models.Model):
  balance_transaction = models.ForeignKey(
      BalanceTransaction, on_delete=models.CASCADE)
  description = models.TextField()
  amount = MoneyField(
      max_digits=10, decimal_places=2, default_currency='USD')


class Charge(models.Model):
  charge_id = models.CharField(max_length=200, db_index=True)
  balance_transaction = models.ForeignKey(
      BalanceTransaction, on_delete=models.CASCADE)
  amount = MoneyField(
      max_digits=10, decimal_places=2, default_currency='USD')
  created = models.DateTimeField()
  cc_last_4 = models.CharField(max_length=4)
  cc_brand = models.CharField(max_length=20)
  WARN_IF_THESE_ARE_NONZERO = ['amount_refunded', 'application_fee']
