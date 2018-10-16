from datetime import timedelta

from django.db import models
from djmoney.models.fields import MoneyField
from djmoney.money import Money

from xxero.api import API


class BankAccountManager(models.Manager):
  def sync_account(self, account_dict):
    account_id = account_dict['AccountID']
    account = self.filter(account_id=account_id).first()
    if not account:
      account = BankAccount(account_id=account_id)
    if account.name != account_dict['Name']:
      account.name = account_dict['Name']
      account.save()
    return account


class BankAccount(models.Model):
  account_id = models.UUIDField()
  name = models.CharField(max_length=200)

  objects = BankAccountManager()


class ContactManager(models.Manager):
  def sync_contact(self, contact_dict):
    contact_id = contact_dict['ContactID']
    contact = self.filter(contact_id=contact_id).first()
    if not contact:
      contact = Contact(contact_id=contact_id)
    if contact.name != contact_dict['Name']:
      contact.name = contact_dict['Name']
      contact.save()
    return contact


class Contact(models.Model):
  contact_id = models.UUIDField()
  name = models.CharField(max_length=200)

  objects = ContactManager()


SPEND = 'SPEND'
RECEIVE = 'RECEIVE'
XERO_TYPE_CHOICES = (
    (SPEND, SPEND),
    (RECEIVE, RECEIVE))


class TransactionManager(models.Manager):
  def sync_transactions(self, from_date, to_date, api=API()):
    """ By convention, to_date is exclusive. """
    on = from_date
    while on < to_date:
      for transaction_dict in api.bank_transactions(on):
        self.sync_transaction(transaction_dict)
      on += timedelta(days=1)

  def sync_transaction(self, transaction_dict):
    bank_transaction_id = transaction_dict['BankTransactionID']
    transaction = self.filter(bank_transaction_id=bank_transaction_id).first()
    if not transaction:
      transaction = Transaction(bank_transaction_id=bank_transaction_id)
    transaction.bank_account = BankAccount.objects.sync_account(
        transaction_dict['BankAccount'])
    transaction.xero_type = transaction_dict['Type']
    transaction.contact = Contact.objects.sync_contact(
        transaction_dict['Contact'])
    transaction.when = transaction_dict['Date'].date()
    transaction.amount = Money(
        str(transaction_dict['Total']), transaction_dict['CurrencyCode'])
    transaction.save()
    return transaction


class Transaction(models.Model):
  bank_transaction_id = models.UUIDField()
  bank_account = models.ForeignKey(BankAccount, on_delete=models.CASCADE)
  xero_type = models.CharField(max_length=20, choices=XERO_TYPE_CHOICES)
  contact = models.ForeignKey(Contact, on_delete=models.CASCADE)
  when = models.DateField()
  amount = MoneyField(max_digits=10, decimal_places=2, default_currency='USD')

  objects = TransactionManager()
