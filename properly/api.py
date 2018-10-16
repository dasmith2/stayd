import requests

from django.conf import settings
from django.shortcuts import reverse

from util.network import can_write_net
from util.random_string import random_string


class API(object):
  """ Regarding the clientRequestId, the docs say "when not provided, we will
  generate one." But if you don't include one they return a 500 error with
  content
  [{"type":"required","field":"clientRequestId","message":
      "The 'clientRequestId' field is required!"}] """
  def setup_webhook(self):
    """
    'Evetytime (sic) you call /setupWebhook your webhook configurations are
    replaced.' """
    if can_write_net():
      setup_my_webhook_url = self._url('/setupWebhook')
      call_my_webhook_url = '{}{}'.format(
          settings.THIS_SERVERS_BASE_URL, reverse('properly_webhook'))
      return requests.post(
          setup_my_webhook_url, headers=self._headers(), json={
              'targetAccountId': settings.PROPERLY_TARGET_ACCOUNT_ID,
              'clientRequestId': random_string(7),
              'webhooks': [{
                  'url': call_my_webhook_url,
                  'eventName': '*'}]})

  def _headers(self):
    return {'x-api-key': settings.PROPERLY_API_KEY}

  def _url(self, endpoint):
    if endpoint[0] == '/':
      endpoint = endpoint[1:]
    return '{}/{}'.format(settings.PROPERLY_API_ROOT, endpoint)
