import math
import requests
from requests.exceptions import SSLError
import time

from django.conf import settings

from util.network import can_read_net, can_write_net
from util.html_status_codes import raise_if_not_ok, ServerError


class FrontAPI(object):
  headers = {
      'Authorization': 'Bearer {}'.format(settings.FRONT_JSON_WEB_TOKEN)}

  def send_message(self, message_data, from_channel=None):
    """ See front/api_examples.py#SENT_MESSAGE
    message_data = {'body': 'Hello world!', 'to': ['9176084623']} """
    from_channel = from_channel or settings.DEFAULT_FRONT_SMS_CHANNEL_ID
    function_name = '/channels/{}/messages'.format(from_channel)
    return self._post(function_name, message_data)

  def get_message(self, message_uid):
    """ See front/api_examples.py#MESSAGE This is where we get the convo_id
    from. """
    return self._get('/messages/alt:uid:{}'.format(message_uid))

  def get_convo(self, convo_id):
    return self._get(self._convo_function_name(convo_id))

  def patch_convo(self, convo_id, data):
    return self._patch(self._convo_function_name(convo_id), data)

  def get_channels(self):
    """ This is really only useful in the shell. At this point we just use
    the one channel for everything so there's no need to look anything up. """
    return self._get('/channels')

  def post_contact(self, contact_data):
    return self._post('/contacts', contact_data)

  def get_contact(self, contact_id):
    return self._get(self._contact_function_name(contact_id))

  def get_contacts(self, next_url=None, verbose=False):
    next_url = next_url or '/contacts?sort_by=updated_at&sort_order=desc'
    while next_url:
      if verbose:
        print(next_url)
      data = self._get(next_url).json()
      next_url = data['_pagination']['next']
      for contact in data['_results']:
        yield contact

  def patch_contact(self, contact_id, contact_data):
    return self._patch(self._contact_function_name(contact_id), contact_data)

  def delete_contact(self, contact_id):
    return self._delete(self._contact_function_name(contact_id))

  def _contact_function_name(self, contact_id):
    return '/contacts/{}'.format(contact_id)

  def _convo_function_name(self, convo_id):
    return '/conversations/{}'.format(convo_id)

  def _get(self, function_name):
    if can_read_net():
      url = self._url(function_name)
      return self._do_request(
          lambda: requests.get(url, headers=self.headers), url=url)

  def _patch(self, function_name, data):
    if can_write_net():
      url = self._url(function_name)
      return self._do_request(
          lambda: requests.patch(url, headers=self.headers, json=data),
          url=url, sent_data=data)

  def _post(self, function_name, data):
    if can_write_net():
      url = self._url(function_name)
      return self._do_request(
          lambda: requests.post(url, headers=self.headers, json=data),
          url=url, sent_data=data)

  def _delete(self, function_name):
    if can_write_net():
      url = self._url(function_name)
      return self._do_request(
          lambda: requests.delete(url, headers=self.headers), url=url)

  def _url(self, function_name):
    prefix = 'https://api2.frontapp.com/'
    # This happens in paging.
    if function_name.find(prefix) == 0:
      return function_name
    if function_name[0] == '/':
      function_name = function_name[1:]
    return prefix + function_name

  def _do_request(self, closure, url=None, sent_data=None):
    """ By default, the API is limited to 120 requests in 60 seconds. If you
    need more, just ask us and we will consider raising your quota.

    When the rate limit is exceeded, the server will respond with a 429 Too
    Many Requests HTTP code with the header Retry-After to tell you how many
    seconds you need to wait before you can retry the request. """
    response = None
    try:
      response = closure()
      while response.status_code == 429:
        time.sleep(math.ceil(float(response.headers['Retry-After'])))
        response = closure()
    except (SSLError, ConnectionError) as ex:
      # One time I got
      # SSLError(MaxRetryError("HTTPSConnectionPool(host='api2.frontapp.com',
      # port=443): Max retries exceeded with url: /contacts/crd_dhzgzp (Caused
      # by SSLError(SSLEOFError(8, 'EOF occurred in violation of protocol
      # (_ssl.c:852)'),))",),)
      raise ServerError(ex)
    raise_if_not_ok(response, url=url, sent_data=sent_data)
    return response
