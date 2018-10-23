import os
import time

from django.conf import settings
from xero.auth import PrivateCredentials
from util.network import can_read_net
from xero import Xero
from xero.exceptions import XeroRateLimitExceeded


class API(object):
  def __init__(self):
    self.xero = None

  def get_xero(self):
    can_read_net()
    if not self.xero:
      rsa_path = os.path.join(settings.BASE_DIR, 'xxero/privatekey.pem')
      with open(rsa_path) as keyfile:
        rsa_key = keyfile.read()
      credentials = PrivateCredentials(settings.XERO_CONSUMER_KEY, rsa_key)
      self.xero = Xero(credentials)
    return self.xero

  def bank_transactions(self, on_date):
    return self._do_request(
        lambda: self.get_xero().banktransactions.filter(Date=on_date))

  def bank_transaction(self, transaction_id):
    return self._do_request(
        lambda: self.get_xero().banktransactions.get(transaction_id)[0])

  def _do_request(self, closure):
    """ I noticed a bunch of network related errors happening from time to
    time, so here we go with retries and exponential backoff.
    ConnectionError, MaxRetryError, NewConnectionError,
    gaierror: [Errno -3] Temporary failure in name resolution

    You also get 60 calls in a rolling 60 second window before you hit the rate
    limit.
    """
    attempts = 0
    last_error = None
    while attempts < 4:
      try:
        return closure()
      except (ConnectionError, XeroRateLimitExceeded) as ex:
        last_error = ex
        # 1 second at first, then 5 seconds, then 25 seconds, then give up.
        time.sleep(5 ** attempts)
        attempts += 1
    raise last_error
