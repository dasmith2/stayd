""" There is a stripe library you can use, but I don't trust the API library to
have good error handling, and the Stripe API is easy enough to use with
requests. """
from django.conf import settings
import requests
from requests.auth import HTTPBasicAuth

from util.html_status_codes import is_server_error, get_json, ServerError


class API(object):
  def get_payouts(self, last_id=None):
    for item in self._get_whatevers('payouts'):
      yield item

  def get_payout(self, payout_id):
    return self._get('payouts/{}'.format(payout_id))

  def get_charges(self):
    return self._get('charges')

  def get_charge(self, charge_id):
    return self._get('charges/{}'.format(charge_id))

  def _get_whatevers(self, endpoint):
    last_id = None
    keep_going = True
    while True:
      url = endpoint
      if last_id:
        url += '?starting_after={}'.format(last_id)
      got = self._get(url)
      for item in got['data']:
        yield item
        last_id = item['id']
      if not got['has_more']:
        break

  def _get(self, endpoint):
    url = self._url(endpoint)
    got = requests.get(url, auth=HTTPBasicAuth(settings.STRIPE_API_KEY, ''))
    if is_server_error(got):
      raise ServerError('Stripe', endpoint)
    return get_json(got)

  def _url(self, endpoint):
    return 'https://api.stripe.com/v1/{}'.format(endpoint)
