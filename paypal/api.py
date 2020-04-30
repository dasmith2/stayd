"""
Sandbox. https://api.sandbox.paypal.com
Live. https://api.paypal.com
"""
from django.conf import settings
import requests

from util.html_status_codes import raise_if_server_error


class API(object):
  def __init__(self):
    self.access_token = None

  def send_payout(self, send_data):
    url = self._url('/v1/payments/payouts')
    resp = requests.post(url, headers=self._auth_header(), json=send_data)
    raise_if_server_error(resp)
    return resp.json()

  def get_status(self, payout_batch_id):
    url = self._url('/v1/payments/payouts/{}'.format(payout_batch_id))
    resp = requests.get(url, headers=self._auth_header())
    raise_if_server_error(resp)
    return resp.json()

  def _url(self, sub_url):
    base = settings.PAYPAL_API_BASE_URL
    if base[-1] != '/':
      raise Exception('I expect PAYPAL_API_BASE_URL to have a trailing /')
    if sub_url[0] == '/':
      sub_url = sub_url[1:]
    return base + sub_url

  def _get_access_token(self):
    if not self.access_token:
      url = self._url('/v1/oauth2/token')
      headers = {
          'Accept': 'application/json',
          'Accept-Language': 'en_US',
      }
      data = [('grant_type', 'client_credentials')]
      auth = (settings.PAYPAL_CLIENT_ID, settings.PAYPAL_SECRET)
      resp = requests.post(url, headers=headers, data=data, auth=auth)
      self.access_token = resp.json()['access_token']
    return self.access_token

  def _auth_header(self):
    return {
        'Authorization': 'Bearer {}'.format(self._get_access_token())}
