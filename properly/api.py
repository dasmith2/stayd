import requests

from django.conf import settings
from django.shortcuts import reverse

from util.network import can_write_net
from util.random_string import random_string


class API(object):
  def job_request_create(self, data):
    return self._send_api_event('jobRequest.create', data)

  def job_request_update(self, data):
    return self._send_api_event('jobRequest.update', data)

  def _send_api_event(self, namespace_action, data):
    return self._post(self._url('/apiEvent'), {namespace_action: [data]})

  def setup_webhook(self):
    """
    'Evetytime (sic) you call /setupWebhook your webhook configurations are
    replaced.'
    Regarding the clientRequestId, the docs say "when not provided, we will
    generate one." But if you don't include one they return a 500 error with
    content
    [{"type":"required","field":"clientRequestId","message":
    "The 'clientRequestId' field is required!"}] """
    if can_write_net():
      call_my_webhook_url = '{}{}'.format(
          settings.THIS_SERVERS_BASE_URL, reverse('properly_webhook'))
      return self._post(self._url('/setupWebhook'), {
          'webhooks': [{
              'url': call_my_webhook_url,
              'eventName': '*'}]})

  def _post(self, url, data):
    # if can_write_net():  # Put this in when we're far enough along in
    # development.
    return requests.post(
        url, headers=self._headers(),
        json=self._json_request(data))

  def _json_wrapper(self, data):
    send_json = {
        'targetAccountId': settings.PROPERLY_TARGET_ACCOUNT_ID,
        'clientRequestId': random_string(7)}
    send_json.update(data)
    return send_json

  def _headers(self):
    return {'x-api-key': settings.PROPERLY_API_KEY}

  def _url(self, endpoint):
    if endpoint[0] == '/':
      endpoint = endpoint[1:]
    return '{}/{}'.format(settings.PROPERLY_API_ROOT, endpoint)
