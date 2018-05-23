"""
By default, the API is limited to 120 requests in 60 seconds. If you need
more, just ask us and we will consider raising your quota.

When the rate limit is exceeded, the server will respond with a 429 Too Many
Requests HTTP code with the header Retry-After to tell you how many seconds
you need to wait before you can retry the request.
"""

import requests
from django.conf import settings


class Front(object):
  headers = {
      'Authorization': 'Bearer {}'.format(settings.FRONT_JSON_WEB_TOKEN)}

  def _url(self, function_name):
    return 'https://api2.frontapp.com{}'.format(function_name)

  def _get(self, function_name):
    return requests.get(self._url(function_name), headers=self.headers)

  def get_channels(self):
    return self._get('/channels').json()['_results']

  def send_test_sms(self):
    example_channel = self.get_channels()[-1]  # LA - Shelly Hollands
    example_channel_id = example_channel['id']
    to_me = '1 (917) 608-4623'
    return self.send_sms(to_me, example_channel_id, 'Hello world!')

  def send_sms(self, to, from_channel, content):
    url = self._url('/channels/{}/messages'.format(from_channel))
    data = {
        'body': content,
        'to': [to]}
    if not settings.DEBUG:
      return requests.post(url, headers=self.headers, json=data)
