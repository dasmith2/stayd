from collections import namedtuple
import re

from django.conf import settings
from django.db import models
from django.db.models import Q
from xero.exceptions import XeroBadRequest

from bento.models import (
    Transaction as BentoTransaction, MerchantCategory, CREDIT, FEE)
from commands.models import background_command
from errors.models import log_error
from util.fields import OneToOneOrNoneField
from xxero.api import API
from xxero.models.businesses import Business
from xxero.models.coconuts import Coconut
from xxero.models.contacts import Contact
from xxero.models.tracking import TrackingCategory
from xxero.models.transactions import (
    Transaction as XeroTransaction, AUTHORISED, DELETED)


@background_command
def push_bento_2_xero_background():
  Bento2Transaction.objects.push_bento_2_xero()
  Bento2Transaction.objects.fix_deleted()
  Bento2Transaction.objects.fix_missing_tracking_options()


class Bento2TransactionManager(models.Manager):
  def fix_deleted(self):
    for b2t in self.filter(xero_transaction__status=DELETED):
      b2t.fix_deleted()

  def fix_missing_tracking_options(self, api_lookup=None):
    api_lookup = api_lookup or Business.objects.get_api_lookup()
    should_have_tracking = Q(bento_transaction__card__isnull=False) | Q(
        bento_transaction__building__isnull=False)
    doesnt_have_tracking = Q(
        xero_transaction__lineitem__tracking_options__isnull=True)
    for b2t in self.filter(
        should_have_tracking, doesnt_have_tracking,
        xero_transaction__status=AUTHORISED):
      b2t.fix_missing_tracking_options(api_lookup)

  def push_bento_2_xero(self, api=None):
    Business.objects.init_businesses()

    api = api or API()
    business = Business.objects.get_operator()
    for bento_transaction in BentoTransaction.objects.filter(
        bento2transaction__isnull=True):
      data = self._bento_transaction_2_data(bento_transaction, business, api)
      transaction_dict = None
      try:
        transaction_dict = api.save_bank_transaction(data)
      except XeroBadRequest as ex:
        log_error(
            'XeroBadRequest when calling save_bank_transaction',
            'Bento transaction {} has data\n\n{}\n\nwhich caused\n\n{}'.format(
                bento_transaction.pk, data, ex))
      if transaction_dict:
        xero_transaction = XeroTransaction.objects.sync_transaction(
            transaction_dict, Business.objects.get_operator(), api=api)
        Bento2Transaction.objects.create(
            bento_transaction=bento_transaction,
            xero_transaction=xero_transaction)

  def _bento_transaction_2_data(self, bento_transaction, business, api=None):
    api = api or business.get_api()
    ttype = 'SPEND' if bento_transaction.ttype in [CREDIT, FEE] else 'RECEIVE'
    contact_id = Contact.objects.get_by_name(
        bento_transaction.payee, business, api=api).contact_id
    amount = str(float(abs(bento_transaction.amount.amount)))
    account_code = 'Bento1'
    if bento_transaction.merchant_category:
      mc2c = MerchantCategory2Coconut.objects.filter(
          merchant_category=bento_transaction.merchant_category).first()
      if mc2c:
        account_code = mc2c.coconut.code
    return {
        'Type': ttype,
        'Contact': {'ContactID': str(contact_id)},
        'LineItems': [{
            'AccountCode': account_code,
            'UnitAmount': amount,
            'Tracking': self.tracking_data(bento_transaction, api=api)}],
        'BankAccount': {'AccountID': settings.XERO_BENTO_BANK_ACCOUNT},
        'Date': bento_transaction.transaction_date}

  def tracking_data(self, bento_transaction, api=None):
    options = self.tracking_options(bento_transaction, api)
    return [self._tracking_option_data(option) for option in options]

  def tracking_options(self, bento_transaction, api=None):
    options = []
    if bento_transaction.card:
      card = TrackingCategory.objects.get_by_name('Bento Card', api=api)
      options.append(card.get_option(bento_transaction.card.alias, api=api))
    if bento_transaction.building:
      building = TrackingCategory.objects.get_by_name(
          'Bldg', api=api)
      # Here's where building tracking options may get created with the
      # nickname of the building.
      building_option = building.get_option(
          bento_transaction.building.nickname, api=api)
      if building_option.building != bento_transaction.building:
        building_option.building = bento_transaction.building
        building_option.save()
      options.append(building_option)
    return options

  def _tracking_option_data(self, tracking_option):
    tracking_category = tracking_option.tracking_category
    return {
        'Name': tracking_category.name,
        'Option': tracking_option.name,
        'TrackingCategoryID': str(tracking_category.tracking_category_id),
        'TrackingOptionID': str(tracking_option.tracking_option_id)}


class Bento2Transaction(models.Model):
  bento_transaction = OneToOneOrNoneField(
      BentoTransaction, on_delete=models.PROTECT)
  xero_transaction = models.ForeignKey(
      XeroTransaction, on_delete=models.PROTECT)

  objects = Bento2TransactionManager()

  def fix_deleted(self):
    """ We push bento to xero. The accountant downloads all those transactions
    from Xero as a csv, deletes all the original transactions, imports the csv,
    then sets the coconut on each xero_transaction. This weird workflow is due
    to a Xero technical limitation not allowing the normal tools on API pushed
    transactions. In the process, the tracking categories get dropped. So when
    the original xero_transaction was deleted, we have to find the new
    xero_transaction, and re-add the tracking categories. """
    if not self.xero_transaction.deleted():
      raise Exception(
          'You cant fix deleted on Bento2Transaction {} whose '
          'xero_transaction has status {}'.format(
              self.pk, self.xero_transaction.status))
    non_deleted = self.find_non_deleted_transaction()
    if non_deleted:
      self.xero_transaction = self.find_non_deleted_transaction()
      self.save()

  def find_non_deleted_transaction(self):
    candidates = XeroTransaction.objects.filter(
        bank_account=self.xero_transaction.bank_account,
        xero_type=self.xero_transaction.xero_type,
        when=self.xero_transaction.when,
        amount=self.xero_transaction.amount,
        status=AUTHORISED)
    if candidates.count() == 1:
      return candidates.first()
    if candidates.count() > 1:
      return candidates.filter(bento2transaction__isnull=True).first()

  def fix_missing_tracking_options(self, api_lookup=None):
    """ For example,
    https://go.xero.com/Bank/ViewTransaction.aspx?bankTransactionID=9062cf15-539d-42ff-921a-5ff482191c3a&accountId=7a61b590-80ec-4133-a526-933a7bbdd0aa
    ought to have the 8 Erie bldg tag. At first I tried to update Xero, but
    that caused XeroBadRequest: ValidationException: A validation exception
    occurred (This Bank Transaction cannot be edited as it has been reconciled
    with a Bank Statement.)

    So now I just update my database. """
    business = self.xero_transaction.bank_account.business
    api = business.get_api(api_lookup)
    options = Bento2Transaction.objects.tracking_options(
        self.bento_transaction, api=api)
    line_items = self.xero_transaction.lineitem_set.all()
    if len(line_items) != 1:
      message = (
          'b2t {} has a XeroTransaction with more than one line item. '
          'From where Im sitting that doesnt make sense. I expect to '
          'only fix tracking options on bento2xero transactions in xero '
          'and those should only have 1 line item.').format(self.pk)
      log_error(
          'I cant fix tracking options on more than one line item', message)
    else:
      line_items.first().tracking_options.set(options)

  def add_tracking_to_data(self, data, api):
    data['LineItems'][0]['Tracking'] = Bento2Transaction.objects.tracking_data(
        self.bento_transaction, api=api)


class MerchantCategory2Coconut(models.Model):
  """ When pushing bento transactions to xxero, what coconut should we use? """
  merchant_category = models.ForeignKey(
      MerchantCategory, on_delete=models.CASCADE)
  coconut = models.ForeignKey(Coconut, on_delete=models.CASCADE)

  def __repr__(self):
    return '<MerchantCategory2Coconut {}: "{}" "{}">'.format(
        self.pk, self.merchant_category.name, self.coconut.name)


MC2CValue = namedtuple('MC2CValue', 'merchant_category coconut')


def get_merchant_category_2_coconut():
  mc2c_lookup = {}  # merchant category -> coconut
  for mc2c in MerchantCategory2Coconut.objects.all():
    mc2c_lookup[mc2c.merchant_category] = mc2c.coconut

  mc2c_values = []
  for merchant_category in MerchantCategory.objects.all():
    mc2c_values.append(
        MC2CValue(merchant_category, mc2c_lookup.get(merchant_category, None)))
  return mc2c_values


def handle_merchant_category_2_coconut(request_post):
  merchant_categories = MerchantCategory.objects.all()
  coconuts = Coconut.objects.all()
  merchant_category_lookup = {}
  for merchant_category in merchant_categories:
    merchant_category_lookup[merchant_category.pk] = merchant_category
  coconut_lookup = {}
  for coconut in coconuts:
    coconut_lookup[coconut.pk] = coconut

  merchant_category_id_finder = re.compile(r'merchant_category([-\d]+)')
  for key, coconut_id in request_post.items():
    found = merchant_category_id_finder.match(key)
    if found and coconut_id:
      merchant_category = merchant_category_lookup[int(found.groups()[0])]
      mc2c = MerchantCategory2Coconut.objects.filter(
          merchant_category=merchant_category).first()
      if not mc2c:
        mc2c = MerchantCategory2Coconut(merchant_category=merchant_category)
      mc2c.coconut = coconut_lookup[int(coconut_id)]
      mc2c.save()
