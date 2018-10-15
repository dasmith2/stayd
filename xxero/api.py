import os
from django.conf import settings
from xero.auth import PrivateCredentials
from xero import Xero


class API(object):
  def __init__(self):
    self.xero = None

  def get_xero(self):
    if not self.xero:
      rsa_path = os.path.join(settings.BASE_DIR, 'xxero/privatekey.pem')
      with open(rsa_path) as keyfile:
        rsa_key = keyfile.read()
      credentials = PrivateCredentials(settings.XERO_CONSUMER_KEY, rsa_key)
      self.xero = Xero(credentials)
    return self.xero

  def bank_transactions(self, on_date):
    return self.get_xero().banktransactions.filter(Date=on_date)
