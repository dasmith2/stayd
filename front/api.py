import requests
import time

from django.conf import settings

from errors.models import log_error


class FrontAPI(object):
  headers = {
      'Authorization': 'Bearer {}'.format(settings.FRONT_JSON_WEB_TOKEN)}

  def send_message(self, message_data):
    """
    {'conversation_reference':
        'e5db74381ddfd6cb4374eccd52579eff@frontapp.com',
     'message_uid': 'e5db74381ddfd6cb4374eccd52579eff',
     'status': 'accepted'} """
    from_channel = settings.FRONT_SMS_CHANNEL_ID
    url = self._url('/channels/{}/messages'.format(from_channel))
    return self._do_request(
        lambda: requests.post(url, headers=self.headers, json=message_data))

  def get_convo(self, convo_id):
    return self._do_request(
        lambda: requests.get(self._convo_url(convo_id), headers=self.headers))

  def patch_convo(self, convo_id, data):
    return self._do_request(lambda: requests.patch(
        self._convo_url(convo_id), headers=self.headers, json=data))

  def get_channels(self):
    return self._get('/channels').json()['_results']

  def get_message(self, message_uid):
    return self._get(self._url('/messages/alt:uid:{}'.format(message_uid)))

  def get_contact(self, contact_id):
    url = self._contact_url(contact_id)
    return self._do_request(lambda: requests.get(url, headers=self.headers))

  def post_contact(self, contact_data):
    url = self._url('/contacts')
    return self._do_request(
        lambda: requests.post(url, headers=self.headers, json=contact_data))

  def patch_contact(self, contact_id, contact_data):
    url = self._contact_url(contact_id)
    return self._do_request(
        lambda: requests.patch(url, headers=self.headers, json=contact_data))

  def _url(self, function_name):
    if function_name[0] == '/':
      function_name = function_name[1:]
    return 'https://api2.frontapp.com/{}'.format(function_name)

  def _get(self, function_name):
    url = self._url(function_name)
    return self._do_request(lambda: requests.get(url, headers=self.headers))

  def _contact_url(self, contact_id):
    return self._url('/contacts/{}'.format(contact_id))

  def _convo_url(self, convo_id):
    return self._url('/conversations/{}'.format(convo_id))

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
