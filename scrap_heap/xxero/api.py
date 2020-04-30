import os
import requests
import time
from xml.etree import ElementTree

from django.conf import settings
from xero.auth import PrivateCredentials
from xero.exceptions import XeroBadRequest
from util.network import can_read_net, can_write_net
from xero import Xero
from xero.exceptions import XeroRateLimitExceeded


def operator_api():
  return API()


def example_owner_api():
  return API(settings.XERO_EXEC_RESIDENCE_CONSUMER_KEY)


class ContactExistsAlready(Exception):
  pass


class API(object):
  """ By default this object uses the "operator" consumer key, a.k.a. our
  primary business. But you can also instantiate this class with a different
  consumer key. At this time, the thought is to do one consumer key per
  "owner". """
  def __init__(
      self, consumer_key=settings.XERO_HI_HOWARD_OPERATIONS_CONSUMER_KEY):
    self.xero = None
    self.consumer_key = consumer_key
    self.verbose = False

  def accounts(self):
    return self._do_request(lambda: self.get_xero().accounts.all(), 'accounts')

  def account_by_code(self, code):
    got = self._do_request(
        lambda: self.get_xero().accounts.filter(Code=code), 'account_by_code')
    if len(got):
      return got[0]

  def account_by_name(self, name):
    got = self._do_request(
        lambda: self.get_xero().accounts.filter(Name=name), 'account_by_name')
    if len(got):
      return got[0]

  def save_account(self, data):
    can_write_net()
    if 'Class' in data:
      del data['Class']  # Class cannot be supplied
    if 'AccountID' in data:
      return self._do_request(
          lambda: self.get_xero().accounts.save(data), 'update_account')[0]
    return self._do_request(
        lambda: self.get_xero().accounts.put(data), 'create_account')[0]

  def get_xero(self):
    can_read_net()
    if not self.xero:
      rsa_path = os.path.join(settings.BASE_DIR, 'xxero/privatekey.pem')
      with open(rsa_path) as keyfile:
        rsa_key = keyfile.read()
      credentials = PrivateCredentials(self.consumer_key, rsa_key)
      self.xero = Xero(credentials)
    return self.xero

  def bank_transactions(self, since_date):
    return self._do_request(
        lambda: self.get_xero().banktransactions.filter(since=since_date),
        'bank_transactions')

  def bank_transaction(self, transaction_id):
    return self._do_request(
        lambda: self.get_xero().banktransactions.get(str(transaction_id))[0],
        'bank_transaction')

  def save_bank_transaction(self, data):
    can_write_net()
    if 'BankTransactionID' in data:
      return self._do_request(
          lambda: self.get_xero().banktransactions.save(data),
          'update_bank_transaction')[0]
    return self._do_request(
        lambda: self.get_xero().banktransactions.put(data),
        'create_bank_transaction')[0]

  def contacts(self):
    return self._do_request(lambda: self.get_xero().contacts.all(), 'contacts')

  def contact(self, name):
    # Adding support for case-insensitive queries
    # https://github.com/freakboy3742/pyxero/issues/227 The issue is that if
    # you just do Name=name it does a case sensitive query, but then if you try
    # to create a contact with that name, it does a case insensitive lookup for
    # existing contacts.
    raw_query = 'Name.ToLower().Equals("{}")'.format(name.lower())
    got = self._do_request(
        lambda: self.get_xero().contacts.filter(raw=raw_query), 'contact')
    if len(got):
      return got[0]

  def get_tracking_category_by_name(self, name):
    got = self._do_request(
        lambda: self.get_xero().trackingcategories.filter(Name=name),
        'get_tracking_category_by_name')
    if len(got):
      return got[0]

  def tracking_category(self, tracking_category_id):
    # str in case tracking_category_id is a UUID
    got = self._do_request(lambda: self.get_xero().trackingcategories.get(
        str(tracking_category_id)), 'tracking_category')
    if len(got):
      return got[0]

  def create_tracking_category(self, name):
    can_write_net()
    return self._do_request(
        lambda: self.get_xero().trackingcategories.put({'Name': name}),
        'create_tracking_category')[0]

  def create_tracking_option(self, tracking_category_id, name):
    can_write_net()
    """ Apologies for the reverse engineering of pyxero, but they didn't have a
    function set up for creating tracking options.
    https://developer.xero.com/documentation/api/tracking-categories """
    auth = self.get_xero().trackingcategories.credentials.oauth
    uri = (
        'https://api.xero.com/api.xro/2.0/TrackingCategories'
        '/{}/Options').format(tracking_category_id)
    got = self._do_request(
        lambda: requests.put(uri, auth=auth, json={'Name': name}),
        'create_tracking_option')
    tree = ElementTree.fromstring(got.content)
    for option in tree.findall('.//Option'):
      if option.find('Name').text == name:
        return option.find('TrackingOptionID').text
    raise Exception(
        'Unable to find option {} in {}'.format(
            name, got.content.decode('utf-8')))

  def print_profit_and_loss_report(self):
    uri = 'https://api.xero.com/api.xro/2.0/Reports/ProfitAndLoss'
    auth = self.trackingcategories.credentials.oauth
    print(requests.get(uri, auth=auth).decode('utf-8'))

  def create_contact(self, name):
    can_write_net()
    try:
      return self._do_request(
          lambda: self.get_xero().contacts.put({'Name': name}),
          'create_contact')[0]
    except XeroBadRequest as ex:
      """XeroBadRequest: ValidationException: A validation exception occurred
      (The contact name Test contact name is already assigned to another
      contact.  The contact name must be unique across all active contacts.)"""
      if ex.args[0].find('is already assigned to another contact') >= 0:
        raise ContactExistsAlready(ex.args[0])
      raise ex

  def _do_request(self, closure, api_call_name):
    """ I noticed a bunch of network related errors happening from time to
    time, so here we go with retries and exponential backoff.
    ConnectionError, MaxRetryError, NewConnectionError,
    gaierror: [Errno -3] Temporary failure in name resolution

    You also get 60 calls in a rolling 60 second window before you hit the rate
    limit. Syncing transactions tends to hit this because the transactions in
    the list form don't include line items, which have all the juicy details,
    so each transactions needs a separate call.
    """
    attempts = 0
    last_error = None
    while attempts < 5:
      try:
        to_return = closure()
        if self.verbose:
          print('API call: {}'.format(api_call_name))
        return to_return
      except (ConnectionError, XeroRateLimitExceeded) as ex:
        last_error = ex
        # 1 second at first, then 5 seconds, then 25 seconds, then 125, then
        # 625 = 5 ^ 4, then give up.
        sleep_for = 5 ** attempts
        if self.verbose:
          print('API call {} rate limited. Sleeping for {} seconds'.format(
              api_call_name, sleep_for))
        time.sleep(sleep_for)
        attempts += 1
    raise last_error
