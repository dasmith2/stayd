import requests
import time

from django.conf import settings

from errors.models import log_error


class FrontAPI(object):
  headers = {
      'Authorization': 'Bearer {}'.format(settings.FRONT_JSON_WEB_TOKEN)}

  def send_message(self, message_data):
    """ See front/api_examples.py#SENT_MESSAGE
    message_data = {'body': 'Hello world!', 'to': ['9176084623']} """
    from_channel = settings.FRONT_SMS_CHANNEL_ID
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

  def patch_contact(self, contact_id, contact_data):
    return self._patch(self._contact_function_name(contact_id), contact_data)

  def _contact_function_name(self, contact_id):
    return '/contacts/{}'.format(contact_id)

  def _convo_function_name(self, convo_id):
    return '/conversations/{}'.format(convo_id)

  def _get(self, function_name):
    url = self._url(function_name)
    return self._do_request(lambda: requests.get(url, headers=self.headers))

  def _patch(self, function_name, data):
    url = self._url(function_name)
    return self._do_request(
        lambda: requests.patch(url, headers=self.headers, json=data))

  def _post(self, function_name, data):
    url = self._url(function_name)
    return self._do_request(
        lambda: requests.post(url, headers=self.headers, json=data))

  def _url(self, function_name):
    prefix = 'https://api2.frontapp.com/'
    if function_name[0] == '/':
      function_name = function_name[1:]
    if function_name.find(prefix) >= 0:
      # Common mistake. Happens if you, say, self._get(self._url(...))
      raise Exception(prefix + function_name)
    return prefix + function_name

  def _do_request(self, closure):
    """ By default, the API is limited to 120 requests in 60 seconds. If you
    need more, just ask us and we will consider raising your quota.

    When the rate limit is exceeded, the server will respond with a 429 Too
    Many Requests HTTP code with the header Retry-After to tell you how many
    seconds you need to wait before you can retry the request. """
    response = closure()
    while response.status_code == 429:
      log_error(
          'Rate limiting on the front API', '{}'.format(response.headers))
      time.sleep(int(response.headers['Retry-After']))
      response = closure()
    return response
