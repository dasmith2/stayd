from json import JSONDecodeError
import requests

from django.conf import settings
from django.http import Http404

from guests.models import Guest
from rentals.models import Rental
from reservations.models import Reservation
from reservations.syncer import ReservationManagerIsDown
from util.html_status_codes import is_server_error, raise_if_not_ok
from util.network import can_read_net, can_write_net


class GuestyAPI(object):
  def __init__(self):
    self.reservation_status = 'confirmed'

  def get_calendar(self, guesty_rental_id, from_date, to_date):
    """ This is used for seeing if blocks are correct, but you can also use it
    to see price per night. """
    url = '/listings/{}/calendar?from={}&to={}'.format(
        guesty_rental_id, from_date, to_date)
    got = self.get(url)
    raise_if_not_ok(got)
    return got.json()

  def block(self, guesty_id, night, note):
    return self._block_helper(guesty_id, night, 'unavailable', note)

  def unblock(self, guesty_id, night):
    return self._block_helper(guesty_id, night, 'available', '')

  def _block_helper(self, guesty_id, night, status, note):
    """ https://docs.guesty.com/#update-calendars """
    data = {
        'listings': guesty_id, 'from': str(night), 'to': str(night),
        'status': status, 'note': note}
    got = self.put('/listings/calendars', data)
    raise_if_not_ok(got)
    return {}  # This doesn't actually return any data.

  def get_one(self, type_of_thing, guesty_id, allowed_in_runserver=False):
    if type_of_thing is Rental or type_of_thing == 'Rental':
      endpoint = 'listings'
    elif type_of_thing is Reservation or type_of_thing == 'Reservation':
      endpoint = 'reservations'
    elif type_of_thing is Guest or type_of_thing == 'Guesty':
      endpoint = 'guests'
    else:
      raise Exception('Not sure what to do with a {}'.format(type_of_thing))
    endpoint_and_id = '{}/{}'.format(endpoint, guesty_id)
    got = self.get(endpoint_and_id, allowed_in_runserver=allowed_in_runserver)
    if got.status_code == 404:
      raise Http404('{} doesnt exist.'.format(endpoint_and_id))
    elif got.status_code == 403:  # Forbidden?!
      raise Exception(
          'We got a guesty_id that returns 403 forbidden: {}'.format(
              guesty_id))
    elif is_server_error(got):
      raise ReservationManagerIsDown(got.status_code)
    elif got.status_code != 200:
      msg_format = (
          'Got unexpected status code from guesty: {}\n\n'
          'Trying to retrieve {}\n\n'
          '{}')
      raise Exception(msg_format.format(
          got.status_code, guesty_id, got.content))
    try:
      got_json = got.json()
    except JSONDecodeError:
      raise Exception('Guesty returned invalid json!', '{} {}'.format(
          type_of_thing, guesty_id))
    if 'log' in got_json:
      # The log is useless and gets quite large. This makes working in the
      # shell a little easier. I also do this in guesty_webhook in
      # guesty.views.
      del got_json['log']
    return got_json

  def get_many_url(
      self, type_of_thing, skip, limit, from_date=None, to_date=None):
    """ from_date and to_date are only for pulling back a bunch of reservations
    for test purposes. """
    if type_of_thing is Rental:
      url_start = 'listings?'
    elif type_of_thing is Reservation:
      def _checkin_arg(operator, reference_date):
        if reference_date:
          return ''.join([
              ',{"field":"createdAt","operator":"',
              operator,
              '","value":["',
              reference_date.strftime('%Y-%m-%d'),
              '"]}'])
        return ''
      url_start = ''.join([
          'reservations?filters=[',
          '{"field":"status","operator":"$eq","value":"' + (
              self.reservation_status + '"}'),
          _checkin_arg('$gte', from_date),
          _checkin_arg('$lte', to_date),
          ']&'])
    elif type_of_thing == 'Webhook':
      raise Exception(
          'Webhooks don\'t have paging, so just get_all(\'Webhook\')')
    else:
      raise Exception('Not sure what to do with a {}'.format(type_of_thing))
    return '{}skip={}&limit={}'.format(url_start, skip, limit)

  def get_many(
      self, type_of_thing, skip, limit, from_date=None, to_date=None,
      allowed_in_runserver=False):
    if (from_date or to_date) and type_of_thing is not Reservation:
      raise ValueError(
          'from_date and to_date only apply to reservations, not {}'.format(
              type_of_thing))
    url = self.get_many_url(type_of_thing, skip, limit, from_date, to_date)
    got = self.get(url, allowed_in_runserver=allowed_in_runserver)
    raise_if_not_ok(got)
    return got.json()['results']

  def get_all(self, type_of_thing):
    if type_of_thing == 'Webhook':
      got = self.get('webhooks')
      raise_if_not_ok(got)
      return got.json()

    to_return = []

    limit = 25
    skip = 0
    results = self.get_many(type_of_thing, skip, limit)
    while len(results):
      to_return.extend(results)
      skip += len(results)
      results = self.get_many(type_of_thing, skip, limit)

    return to_return

  def get(self, url, print_curl=False, allowed_in_runserver=False):
    if can_read_net(allowed_in_runserver=allowed_in_runserver):
      full_url = self._guesty_url(url)
      if print_curl:
        args = (full_url,) + self._guesty_auth()
        print('curl {} -u {}:{}'.format(*args))
      return requests.get(full_url, auth=self._guesty_auth())

  def post(self, url, data):
    if can_write_net():
      # But only production can write to guesty. I put this in place after
      # I accidentally wrote a nonsense email address to production by creating
      # an id_verify.models.Submission while working on id verification.
      return requests.post(
          self._guesty_url(url), json=data, auth=self._guesty_auth())

  def put(self, url, data):
    if can_write_net():
      return requests.put(
          self._guesty_url(url), json=data, auth=self._guesty_auth())

  def delete(self, url):
    if can_write_net():
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
