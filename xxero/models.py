from datetime import timedelta
import re

from django.db import models
from djmoney.models.fields import MoneyField
from djmoney.money import Money

from xxero.api import API


class BankAccountManager(models.Manager):
  def sync_account(self, account_dict):
    account_id = account_dict['AccountID']
    name = account_dict['Name']
    account = self.filter(account_id=account_id).first()
    if not account:
      account = self.filter(name=name).first()
      if account:
        if account.account_id:
          raise Exception(
              'I got two bank accounts with the same names and different IDs.')
        # This account probably exists because we heard about it in a transfer
        # where we don't get an id. Now, we've found the id for the bank
        # account with that name.
        account.account_id = account_id
        account.save()
        return account
      account = BankAccount(account_id=account_id)
    if account.name != account_dict['Name']:
      account.name = account_dict['Name']
      account.save()
    return account

  def get_by_name(self, name):
    return self.get_or_create(name=name)[0]


class BankAccount(models.Model):
  account_id = models.UUIDField(
      blank=True, null=True, db_index=True, unique=True, help_text=(
          'This can be null because bank transfers only come back with '
          'a name for the account transfered from.'))
  name = models.CharField(max_length=200, unique=True)

  objects = BankAccountManager()

  def __str__(self):
    return self.name


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
  contact_id = models.UUIDField(db_index=True, unique=True)
  name = models.CharField(max_length=200)

  objects = ContactManager()

  def __str__(self):
    return self.name


SPEND = 'SPEND'
RECEIVE = 'RECEIVE'
RECEIVE_TRANSFER = 'RECEIVE-TRANSFER'
SPEND_TRANSFER = 'SPEND-TRANSFER'
XERO_TYPE_CHOICES = (
    (SPEND, SPEND),
    (RECEIVE, RECEIVE),
    (RECEIVE_TRANSFER, RECEIVE_TRANSFER),
    (SPEND_TRANSFER, SPEND_TRANSFER))


class TransactionManager(models.Manager):
  def sync_transactions(self, from_date, to_date, api=API(), verbose=False):
    """ By convention, to_date is exclusive. """
    on = from_date
    while on < to_date:
      if verbose:
        print(on)
      for transaction_dict in api.bank_transactions(on):
        if self._valid_status(transaction_dict):
          # The list version doesn't come back with the LineItems attribute
          # which contains where the money came from / went to.
          if transaction_dict['Type'] in [RECEIVE_TRANSFER, SPEND_TRANSFER]:
            transaction_dict = api.bank_transaction(
                transaction_dict['BankTransactionID'])
          self.sync_transaction(transaction_dict, verbose=verbose)
      on += timedelta(days=1)

  def _valid_status(self, transaction_dict):
    return transaction_dict['Status'] == 'AUTHORISED'

  def sync_transaction(self, transaction_dict, verbose=False):
    if not self._valid_status(transaction_dict):
      return
    bank_transaction_id = transaction_dict['BankTransactionID']
    if verbose:
      print(bank_transaction_id)
    transaction = self.filter(bank_transaction_id=bank_transaction_id).first()
    if not transaction:
      transaction = Transaction(bank_transaction_id=bank_transaction_id)
    transaction.bank_account = BankAccount.objects.sync_account(
        transaction_dict['BankAccount'])
    transaction.xero_type = transaction_dict['Type']
    if transaction.xero_type in [RECEIVE_TRANSFER, SPEND_TRANSFER]:
      name = self._get_transfer_bank_name(transaction_dict)
      transaction.transfer_bank = BankAccount.objects.get_by_name(name)
    elif transaction.xero_type in ['SPEND', 'RECEIVE']:
      transaction.contact = Contact.objects.sync_contact(
          transaction_dict['Contact'])
    else:
      raise Exception(
          'Not sure how to handle Type {} in transaction {}'.format(
              transaction.xero_type, bank_transaction_id))
    transaction.when = transaction_dict['Date'].date()
    transaction.amount = Money(
        str(transaction_dict['Total']), transaction_dict['CurrencyCode'])
    transaction.save()
    return transaction

  def _get_transfer_bank_name(self, transaction_dict):
    description = transaction_dict['LineItems'][0]['Description']
    finder = re.compile(r'Bank Transfer (from|to) (.+)\.')
    return finder.match(description).groups()[1]


class Transaction(models.Model):
  bank_transaction_id = models.UUIDField()
  bank_account = models.ForeignKey(BankAccount, on_delete=models.CASCADE)
  transfer_bank = models.ForeignKey(
      BankAccount, on_delete=models.CASCADE, null=True, blank=True,
      related_name='transfer_bank', help_text=(
          'In the case of a RECEIVE-TRANSFER or a SPEND-TRANSFER, what bank '
          'account did this account get money from or send money to, '
          'respectively?'))
  xero_type = models.CharField(max_length=20, choices=XERO_TYPE_CHOICES)
  contact = models.ForeignKey(
      Contact, on_delete=models.CASCADE, null=True, blank=True, help_text=(
          'In the case of a SPEND or a RECEIVE, which contact was on the '
          'other side of the transaction?'))
  when = models.DateField()
  amount = MoneyField(max_digits=10, decimal_places=2, default_currency='USD')

  objects = TransactionManager()

  class Meta:
    ordering = ('-when',)
