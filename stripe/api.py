""" There is a stripe library you can use, but I don't trust the API library to
have good error handling, and the Stripe API is easy enough to use with
requests. """
from django.conf import settings
import requests
from requests.auth import HTTPBasicAuth


class API(object):
  def get_all_charges(self):
    return self._get('charges')

  def get_charge(self, charge_id):
    return self._get('charges/{}'.format(charge_id))

  def _get(self, endpoint):
    return requests.get(self._url(endpoint), auth=HTTPBasicAuth(
        settings.STRIPE_API_KEY, ''))

  def _url(self, endpoint):
    return 'https://api.stripe.com/v1/{}'.format(endpoint)

  def _trim_none(self, thing):
    if isinstance(thing, dict):
      remove_keys = []
      for key, value in thing.items():
        if value is None:
          remove_keys.append(key)
        elif isinstance(value, dict):
          thing[key] = self._trim_none(value)
        elif isinstance(value, list):
          thing[key] = [self._trim_none(item) for item in value]
      for key in remove_keys:
        del thing[key]
    elif isinstace(thing, list):
      return [self._trim_none(item) for item in thing]
    return thing
