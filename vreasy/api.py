from datetime import timedelta
import re

from django.utils.timezone import localtime
from django.conf import settings
import requests

# From vreasy.com/docs/public-api/
# "use the api-key as the username with no password"
AUTH = (settings.VREASY_API_KEY, '')

WEBHOOK_URL = 'https://stayd-stage.herokuapp.com/save_event'


class VreasyAPI(object):
  """ If you're getting a 500 on a get, you can plug the url directly into a
  browser and get more details. They have a UI for their API, which is nice.
  """

  def get_properties(self):
    return self._get_paginated_results(self._api_url('properties'))

  def get_recently_modified_reservations(self, since_days_ago=7):
    url = self._api_url(
        'reservations?status=CONFIRMED&last_updated={}&expand=guest'.format(
            self._api_dt(-since_days_ago)))
    return self._get_paginated_results(url)

  def get_reservation(self, portal_uid):
    return self._strip_empty(
        self._get('reservations?portal_uid={}'.format(portal_uid)).json()[0])

  def get_currency(self, currency_id):
    # The API doesn't let you filter on id for some reason.
    currencies = self._get('currencies').json()
    return [c for c in currencies if c['id'] == currency_id][0]

  def _get_paginated_results(self, url):
    response = self._get_url(url)
    results = [self._strip_empty(r) for r in response.json()]
    pagination_url = self._get_next_url(response)
    if pagination_url:
      results.extend(
          self._get_paginated_results(pagination_url))
    return results

  def _api_url(self, action_path):
    if action_path[0] == '/':
      action_path = action_path[1:]
    return 'https://www.vreasy.com/api/' + action_path

  def _api_dt(self, days_delta):
    # For instance, '2018-03-28T13:37:53.027284-04:00'
    iso_format = (localtime() + timedelta(days=days_delta)).isoformat()
    # For instance, '2018-03-28T13:37:53-04:00'
    no_decimal = re.compile(r'\.\d+').sub('', iso_format)
    return no_decimal

  def _get_next_url(self, response):
    # Pagination. Example: got.headers['link'] ->
    # '<https://www.vreasy.com/api/reservations?after=2645750>; rel="next"'
    link = response.headers.get('link', '')
    if link.find('rel="next"') > 0:
      return re.compile(r'<(.+)>').search(link).groups()[0]

  def _strip_empty(self, got):
    del_keys = []
    for key in got.keys():
      if not got[key]:
        del_keys.append(key)
    for key in del_keys:
      del got[key]
    return got

  def _get_url(self, url):
    return requests.get(url, auth=AUTH)

  def _get(self, endpoint):
    return requests.get(self._api_url(endpoint), auth=AUTH)

  def _post(self, endpoint, data):
    return requests.post(self._api_url(endpoint), json=data, auth=AUTH)

  def create_reservation_subscription(self, event='reservation_create'):
    # This still 404s so it's not much use now is it!
    data = {
        'event': event,
        'protocol': 'https',
        'endpoint': WEBHOOK_URL}

    return self._post('reservations/subscriptions', data)

  def create_listing_subscription(self):
    # Too bad we don't really care about listing changes!
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

    return self._post('listings/subscriptions', data)

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
    return self._get('subscriptions')

  def delete_subscription(self, subscription_id):
    """
    The id is the field called 'id' in the create response, and in
    get_subscriptions.
    """
    url = self._api_url('subscriptions/{}'.format(subscription_id))
    got = requests.delete(url, auth=AUTH)
    return got.status_code == 204
