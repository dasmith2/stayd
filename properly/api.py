import requests

from django.conf import settings
from django.shortcust import reverse


class API(object):
  def setup_webhook(self):
    """
    'Evetytime (sic) you call /setupWebhook your webhook configurations are
    replaced.' """
    webhook_url = '{}{}'.format(
        settings.THIS_SERVERS_BASE_URL, reverse('properly_webhook'))
    requests.post(self._url('/setupWebhook'), headers=self._headers(), json={
        'targetAccountId': settings.PROPERLY_TARGET_ACCOUNT_ID,
        'webhooks': [{
            'url': webhook_url,
            'eventName': '*'}]})

  def _headers(self):
    return {'x-api-key': settings.PROPERLY_API_KEY}

  def _url(self, endpoint):
    if endpoint[0] == '/':
      endpoint = endpoint[1:]
    return '{}/{}'.format(settings.PROPERLY_API_ROOT, endpoint)
