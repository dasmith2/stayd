import requests

from django.conf import settings
from django.http import Http404

from guests.models import Guest
from rentals.models import Rental
from reservations.models import Reservation
from util.tests import is_test

""" This SHOULD be called guesty/api.py#class API, but I didnt' think of all
that until I'd already built a bunch of stuff. """


class GuestyAPIGetter(object):
  def get_one(self, type_of_thing, guesty_id):
    if type_of_thing is Rental:
      endpoint = 'listings'
    elif type_of_thing is Reservation:
      endpoint = 'reservations'
    elif type_of_thing is Guest:
      endpoint = 'guests'
    else:
      raise Exception('Not sure what to do with a {}'.format(type_of_thing))
    endpoint_and_id = '{}/{}'.format(endpoint, guesty_id)
    got = self.get(endpoint_and_id)
    if got.status_code == 404:
      raise Http404('{} doesnt exist.'.format(endpoint_and_id))
    elif got.status_code == 403:  # Forbidden?!
      raise Exception(
          'We got a guesty_id that returns 403 forbidden: {}'.format(
              guesty_id))
    got_json = got.json()
    if 'log' in got_json:
      # The log is useless and gets quite large. This makes working in the
      # shell a little easier.
      del got_json['log']
    return got_json

  def get_many(self, type_of_thing, skip, limit):
    if type_of_thing is Rental:
      url_start = 'listings?'
    elif type_of_thing is Reservation:
      url_start = (
          'reservations?filters='
          '{"field":"status","operator":"$in","value":["confirmed"]}&')
    elif type_of_thing == 'Webhook':
      raise Exception(
          'Webhooks don\'t have paging, so just get_all(\'Webhook\')')
    else:
      raise Exception('Not sure what to do with a {}'.format(type_of_thing))
    url = url_start + 'skip={}&limit={}'.format(skip, limit)
    return self.get(url).json()['results']

  def get_all(self, type_of_thing):
    if type_of_thing == 'Webhook':
      return self.get('webhooks').json()

    to_return = []

    limit = 25
    skip = 0
    results = self.get_many(type_of_thing, skip, limit)
    while len(results):
      to_return.extend(results)
      skip += len(results)
      results = self.get_many(type_of_thing, skip, limit)

    return to_return

  def get(self, url):
    if not is_test():
      return requests.get(self._guesty_url(url), auth=self._guesty_auth())

  def post(self, url, data):
    if not is_test():
      return requests.post(
          self._guesty_url(url), json=data, auth=self._guesty_auth())

  def put(self, url, data):
    if not is_test():
      return requests.put(
          self._guesty_url(url), json=data, auth=self._guesty_auth())

  def delete(self, url):
    if not is_test():
      return requests.delete(self._guesty_url(url), auth=self._guesty_auth())

  def _guesty_url(self, endpoint):
    if endpoint and endpoint[0] == '/':
      endpoint = endpoint[1:]
    return 'https://api.guesty.com/api/v2/' + endpoint

  def _guesty_auth(self):
    # "Use your API key as the username and secret as the password."
    if not settings.GUESTY_KEY or not settings.GUESTY_SECRET:
      raise Exception(
          'You need the GUESTY_KEY and GUESTY_SECRET settings. '
          'See stayd/settings.py')
    return (settings.GUESTY_KEY, settings.GUESTY_SECRET)
