from datetime import date, timedelta
import re

from django.db import models
from django.utils.timezone import make_aware
from djmoney.money import Money
from djmoney.models.fields import MoneyField

from commands.models import background_command
from errors.models import log_error
from reservations.models import Reservation, ReservationLineItem
from util.timezone import now
from xxero.api import API
from xxero.models.businesses import Business
from xxero.models.coconuts import BankAccount, Coconut
from xxero.models.contacts import Contact
from xxero.models.tracking import TrackingOption


@background_command
def sync_transactions_background():
  """
  The accountant aims to close the books every week, meaning transactions more
  than a week ago shouldn't be getting modified all that often. When they do we
  can perform a manual sync.
  """
  since = date.today() - timedelta(days=31)
  for business in Business.objects.all():
    Transaction.objects.sync_transactions(since, business)


SPEND = 'SPEND'
RECEIVE = 'RECEIVE'
RECEIVE_TRANSFER = 'RECEIVE-TRANSFER'
SPEND_TRANSFER = 'SPEND-TRANSFER'
XERO_TYPE_CHOICES = (
    (SPEND, SPEND),
    (RECEIVE, RECEIVE),
    (RECEIVE_TRANSFER, RECEIVE_TRANSFER),
    (SPEND_TRANSFER, SPEND_TRANSFER))


DELETED = 'DELETED'
AUTHORISED = 'AUTHORISED'
STATUS_CHOICES = (
    (DELETED, DELETED),
    (AUTHORISED, AUTHORISED))


class TransactionManager(models.Manager):
  def sync_transactions(self, since_date, business, api=None, verbose=False):
    api = api or business.get_api()
    api.verbose = verbose
    for transaction_dict in api.bank_transactions(since_date):
      # bank transactions for a list don't contain, for example, line items. So
      # if we're going to actually sync this transaction we have to load the
      # detailed version which is 1 api call per transaction. Xero rate
      # limiting is pretty brutal, so it's important that we only sync
      # transactions when necessary.
      bank_transaction_id = transaction_dict['BankTransactionID']
      existing = self.filter(bank_transaction_id=bank_transaction_id).first()
      updated_at = make_aware(transaction_dict['UpdatedDateUTC'])
      status = transaction_dict['Status']

      if existing and existing.updated_at == updated_at:
        if verbose:
          print('{} unchanged.'.format(bank_transaction_id))
        continue
      elif status == DELETED and not existing:
        if verbose:
          print('{} is deleted and will never be synced.'.format(
              bank_transaction_id))
        continue
      elif not existing:
        if verbose:
          print('Syncing {} for the first time'.format(
              bank_transaction_id, status))
      else:
        if verbose:
          print('{} updated on {}. Resyncing.'.format(
              bank_transaction_id, updated_at.date()))

      if status == DELETED:
        existing.status = DELETED
        existing.status_check_at = now()
        existing.save()
      elif status == AUTHORISED:
        # This is the API call I avoid when possible.
        transaction_dict = api.bank_transaction(bank_transaction_id)
        self.sync_transaction(transaction_dict, business, api=api)
      else:
        log_error('Not sure what to do with xero transaction status {}'.format(
            status))

  def sync_transaction_by_id(self, business, bank_transaction_id):
    api = business.get_api()
    transaction_dict = api.bank_transaction(bank_transaction_id)
    return self.sync_transaction(transaction_dict, business, api=api)

  def sync_transaction(self, transaction_dict, business, api=None):
    bank_transaction_id = transaction_dict['BankTransactionID']
    transaction = self.filter(bank_transaction_id=bank_transaction_id).first()
    if not transaction:
      transaction = Transaction(bank_transaction_id=bank_transaction_id)
    transaction.bank_account = BankAccount.objects.sync_account(
        transaction_dict['BankAccount'], business)
    transaction.xero_type = transaction_dict['Type']
    if transaction.xero_type in [RECEIVE_TRANSFER, SPEND_TRANSFER]:
      name = self._get_transfer_bank_name(transaction_dict)
      bank_account = BankAccount.objects.get_by_name_and_business(
          name, business)
      transaction.transfer_bank = bank_account
    elif transaction.xero_type in ['SPEND', 'RECEIVE']:
      transaction.contact = Contact.objects.sync_contact(
          transaction_dict['Contact'], business)
    else:
      raise Exception(
          'Not sure how to handle Type {} in transaction {}'.format(
              transaction.xero_type, bank_transaction_id))
    transaction.when = transaction_dict['Date'].date()
    transaction.reference = transaction_dict.get('Reference', None)
    transaction.amount = Money(
        str(transaction_dict['Total']), transaction_dict['CurrencyCode'])
    transaction.status = transaction_dict['Status']
    transaction.status_check_at = now()
    transaction.updated_at = make_aware(transaction_dict['UpdatedDateUTC'])
    transaction.save()
    transaction.sync_line_items(business, transaction_dict, api)
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
  when = models.DateField(db_index=True)
  amount = MoneyField(max_digits=10, decimal_places=2, default_currency='USD')
  status = models.CharField(
      max_length=50, null=True, blank=True, choices=STATUS_CHOICES)
  status_check_at = models.DateTimeField(null=True, blank=True)
  updated_at = models.DateTimeField(null=True, blank=True, help_text=(
      'Xero doesnt do webhooks and the rate limiting is brutal.'))
  reference = models.TextField(null=True, blank=True, help_text=(
      'Literally the Xero reference field on a Xero transaction.'))
  reservations = models.ManyToManyField(Reservation, help_text=(
      'What reservations, if any, does this transaction help pay for? '
      'Usually one Airbnb reservation is paid for in a single transaction, '
      'but there are multiple transactions for the same reservation and '
      'single transactions for multiple reservations.'))

  objects = TransactionManager()

  def admin_url(self):
    return (
        'https://go.xero.com/Bank/ViewTransaction.aspx?'
        'bankTransactionID={}&accountId={}').format(
            self.bank_transaction_id, self.bank_account.account_id)

  def is_debit(self):
    return self.xero_type in [SPEND, SPEND_TRANSFER]

  def is_credit(self):
    return self.xero_type in [RECEIVE, RECEIVE_TRANSFER]

  def check_status(self, api=None):
    api = api or API()
    self.status = api.bank_transaction(self.bank_transaction_id)['Status']
    self.status_check_at = now()
    self.save()
    return self.status

  def deleted(self):
    return self.status == DELETED

  class Meta:
    ordering = ('-when',)

  def __repr__(self):
    return '<(Xero)Transaction {}: {} {}>'.format(
        self.pk, self.when, self.amount)

  def sync(self):
    return Transaction.objects.sync_transaction_by_id(
        self.bank_account.business, self.bank_transaction_id)

  def sync_line_items(self, business, transaction_dict, api):
    existing_li_ids = []
    for line_item_data in transaction_dict['LineItems']:
      line_item_id = line_item_data['LineItemID']
      existing_li_ids.append(line_item_id)
      li = self.lineitem_set.filter(line_item_id=line_item_id).first()
      if not li:
        li = LineItem(transaction=self, line_item_id=line_item_id)
      li.amount = Money(
          line_item_data['LineAmount'], transaction_dict['CurrencyCode'])
      coconut_code = line_item_data.get('AccountCode', None)
      if coconut_code:
        li.coconut = Coconut.objects.get_by_code(coconut_code, api)
      li.save()

      options = []
      bank_transaction_id = transaction_dict['BankTransactionID']
      for tracking_data in line_item_data['Tracking']:
        options.append(TrackingOption.objects.sync_option(
            business, tracking_data, bank_transaction_id))
      li.tracking_options.set(options)

    self.lineitem_set.exclude(line_item_id__in=existing_li_ids).delete()


class LineItem(models.Model):
  transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE)
  line_item_id = models.UUIDField()
  amount = MoneyField(max_digits=10, decimal_places=2, default_currency='USD')
  coconut = models.ForeignKey(
      Coconut, on_delete=models.PROTECT, null=True, blank=True, help_text=(
          'Every line item SHOULD have a coconut evenutally. Thats the whole '
          'challenge I guess.'))
  tracking_options = models.ManyToManyField(TrackingOption)
  reservation_line_item = models.ForeignKey(
      ReservationLineItem, null=True, blank=True, on_delete=models.PROTECT,
      help_text=(
          'When a transaction pays for a reservation, the line items of that '
          'transaction may line up with the line items of the reservation.'))

  def __repr__(self):
    return '<LineItem {}: {}>'.format(self.pk, self.amount)
