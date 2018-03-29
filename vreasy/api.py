from datetime import timedelta
import re

from django.utils.timezone import localtime
from django.conf import settings
import requests
from reservations.serializers import ReservationSerializer
from reservations.models import Reservation

# From vreasy.com/docs/public-api/
# "use the api-key as the username with no password"
auth = (settings.VREASY_API_KEY, '')

WEBHOOK_URL = 'https://stayd-stage.herokuapp.com/save_event'


class VreasyAPI(object):
  def api_url(self, action_path):
    if action_path[0] == '/':
      action_path = action_path[1:]
    return 'https://www.vreasy.com/api/' + action_path

  def get(self, endpoint):
    return requests.get(self.api_url(endpoint), auth=auth)

  def post(self, endpoint, data):
    return requests.post(self.api_url(endpoint), json=data, auth=auth)

  def get_properties(self):
    return self.get('properties').json()

  def _api_dt(self, days_delta):
    # For instance, '2018-03-28T13:37:53.027284-04:00'
    iso_format = (localtime() + timedelta(days=days_delta)).isoformat()
    # For instance, '2018-03-28T13:37:53-04:00'
    no_decimal = re.compile(r'\.\d+').sub('', iso_format)
    return no_decimal

  def get_weeks_reservations(self):
    url = 'reservations?status=CONFIRMED&start={}&end={}'.format(
        self._api_dt(-7), self._api_dt(0))
    reservations_response = self.get(url)
    return [self._strip_empty(r) for r in reservations_response.json()]

  def get_channels(self):
    return self.get('channels')

  def create_reservation_subscription(self, event='reservation_create'):
    # reservation_create, reservation_update
    data = {
      'event': event,
      'protocol': 'https',
      'endpoint': WEBHOOK_URL}

    return self.post('reservations/subscriptions', data)

  def create_listing_subscription(self):
    """
    {'api_key': {},
     'api_key_id': 2778,
     'created_at': '2018-03-28 15:26:26',
     'endpoint': 'https://stayd-stage.herokuapp.com/save_event',
     'event': 'listing_update',
     'id': 123255,
     'protocol': 'https',
     'resource_id': None,
     'resource_type': 'listing',
     'updated_at': '2018-03-28 15:26:26'}
    """
    data = {
      'event': 'listing_update',
      'protocol': 'https',
      'endpoint': WEBHOOK_URL}

    return self.post('listings/subscriptions', data)

  def get_subscriptions(self):
    """
    [{'api_key': {},
      'api_key_id': 2778,
      'created_at': '2018-03-28 15:26:26',
      'endpoint': 'https://stayd-stage.herokuapp.com/save_event',
      'event': 'listing_update',
      'id': 123255,
      'protocol': 'https',
      'resource_id': None,
      'resource_type': 'listing',
      'updated_at': '2018-03-28 15:26:26'}]
    """
    return self.get('subscriptions')

  def delete_subscription(self, subscription_id):
    """
    The id is the field called 'id' in the create response, and in
    get_subscriptions.
    """
    url = self.api_url('subscriptions/{}'.format(subscription_id))
    got = requests.delete(url, auth=auth)
    return got.status_code == 204

  def _strip_empty(self, got):
    del_keys = []
    for key in got.keys():
      if not got[key]:
        del_keys.append(key)
    for key in del_keys:
      del got[key]
    return got

  def get_reservation(self, portal_uid):
    url = self.api_url('reservations?portal_uid={}'.format(portal_uid))
    return self._strip_empty(requests.get(url).json()[0])
