import logging

from django.conf import settings
import json
import requests

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


class MockPaypalApi(PaypalAPI):
  """
  OK look, I know you're not supposed to make RPC calls in your tests. But
  sending a payment is fast, and this api can get tricky, so I like the idea
  of leaving the send in the actual api. But then it takes a long time, like
  10 seconds or so, for the status to update on the actual API so we really
  do need to mock get_status.
  """
  def get_status(self, payout_batch_id):
    return json.loads("""
{"batch_header": {"amount": {"currency": "USD", "value": "1.0"},
  "batch_status": "SUCCESS",
  "fees": {"currency": "USD", "value": "0.25"},
  "payout_batch_id": "SWZCNHCAR7ST8",
  "sender_batch_header": {"email_subject": "You just got paid by Stayd",
   "sender_batch_id": "5"},
  "time_completed": "2018-02-28T17:10:37Z",
  "time_created": "2018-02-28T17:10:21Z"},
 "items": [{"errors": {"details": [],
    "information_link":
    "https://developer.paypal.com/docs/api/payments.payouts-batch/#errors",
    "message":"This receiver is not registered.",
    "name": "RECEIVER_UNREGISTERED"},
   "links": [{"encType": "application/json",
     "href":
     "https://api.sandbox.paypal.com/v1/payments/payouts-item/5NWWQ5Z6EUQ",
     "method": "GET",
     "rel": "item"}],
   "payout_batch_id": "SWZCNHCAR7ST8",
   "payout_item": {"amount": {"currency": "USD", "value": "1.0"},
    "note": "This is a note on an individual payment",
    "receiver": "dasmith2@gmail.com",
    "recipient_type": "EMAIL",
    "sender_item_id": "5"},
   "payout_item_fee": {"currency": "USD", "value": "0.25"},
   "payout_item_id": "5NWBQWQ5Z6EUQ",
   "time_processed": "2018-02-28T17:10:34Z",
   "transaction_id": "21846482A3831715D",
   "transaction_status": "UNCLAIMED"}],
 "links": [{"encType": "application/json",
   "href":
   "https://api.paypal.com/v1/payments/payouts/SR7ST8?page_size=10&page=1",
   "method": "GET",
   "rel": "self"}]}
     """)
