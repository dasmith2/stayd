""" There is a stripe library you can use, but I don't trust the API library to
have good error handling, and the Stripe API is easy enough to use with
requests. """
from django.conf import settings
import requests
from requests.auth import HTTPBasicAuth

from util.html_status_codes import get_json, raise_if_server_error


class API(object):
  """ You're, like, wait aren't you pulling back ALL charges every time you run
  get_charges?! Don't worry, _get_whatevers yields the next charge (or
  whatever) as you ask for it. Stripe promises to "return objects in reverse
  chronological order" in pages. So whoever called get_charges is responsible
  to notice when we've gone too far back in time and simply stop asking for
  more charges which will cause no more pages of data to be retrieved. """
  def get_payouts(self):
    return self._get_whatevers('payouts')

  def get_payout(self, payout_id):
    return self._get('payouts/{}'.format(payout_id))

  def get_balance_transactions(self, payout_id):
    return self._get_whatevers('balance/history?payout={}'.format(payout_id))

  def get_balance_transaction(self, balance_transaction_id):
    return self._get('balance/history/{}'.format(balance_transaction_id))

  def get_charges(self):
    return self._get_whatevers('charges')

  def get_charge(self, charge_id):
    return self._get('charges/{}'.format(charge_id))

  def get_refunds(self, charge_id):
    return self._get_whatevers('refunds?charge={}'.format(charge_id))

  def _get_whatevers(self, endpoint):
    last_id = None
    while True:
      url = endpoint
      if last_id:
        if url.find('?') == -1:
          url += '?'
        else:
          url += '&'
        # This variable has exactly the most confusing name possible. The
        # results are returned in reverse chronological order, but
        # starting_after isn't talking about the date. It's talking about the
        # order in the results. So if you say starting_after=some id related to
        # June 1, then this will return only results before June 1 haha
        url += 'starting_after={}'.format(last_id)
      got = self._get(url)
      for item in got['data']:
        yield item
        last_id = item['id']
      if not got['has_more']:
        break

  def _get(self, endpoint):
    url = self._url(endpoint)
    got = requests.get(url, auth=HTTPBasicAuth(settings.STRIPE_API_KEY, ''))
    raise_if_server_error(got, url=endpoint)
    return get_json(got)

  def _url(self, endpoint):
    return 'https://api.stripe.com/v1/{}'.format(endpoint)
