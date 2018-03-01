import requests
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


class PaypalAPI(object):
  def send_payout(self, send_data):
    url = self._api_path('/v1/payments/payouts')

    resp = requests.post(url, headers=self._auth_header(), json=send_data)
    data = resp.json()
    if 'batch_header' not in data:
      logger.error((
          'A Paypal payout came back with unexpected results! It probably '
          'didn\'t send. {} had contents {}').format(resp, data))
    return data

  def get_status(self, payout_batch_id):
    url = self._api_path(
        '/v1/payments/payouts/{}'.format(payout_batch_id))

    resp = requests.get(url, headers=self._auth_header())
    return resp.json()

  def _api_path(self, sub_url):
    base = settings.PAYPAL_API_BASE_URL
    if len(sub_url) and sub_url[0] == '/' and base[-1] == '/':
      sub_url = sub_url[1:]
    return base + sub_url

  def _get_access_token(self):
    url = self._api_path('/v1/oauth2/token')
    headers = {
        'Accept': 'application/json',
        'Accept-Language': 'en_US',
    }
    data = [('grant_type', 'client_credentials')]
    auth = (settings.PAYPAL_CLIENT_ID, settings.PAYPAL_SECRET)
    resp = requests.post(url, headers=headers, data=data, auth=auth)
    return resp.json()['access_token']

  def _auth_header(self):
    return {
        'Authorization': 'Bearer {}'.format(self._get_access_token()),
    }
