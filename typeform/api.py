from django.conf import settings
import requests

from util.html_status_codes import raise_if_not_ok
from util import rrequests


class API(object):
  def set_webhook(self, form_id, tag, url):
    return self._do_put(
        self._webhook_url(form_id, tag), json={'url': url, 'enabled': True})

  def delete_webhook(self, form_id, tag):
    return self._do_delete(self._webhook_url(form_id, tag))

  def _webhook_url(self, form_id, tag):
    return self._url('/forms/{}/webhooks/{}'.format(form_id, tag))

  def _url(self, endpoint):
    if endpoint[0] == '/':
      endpoint = endpoint[1:]
    return 'https://api.typeform.com/{}'.format(endpoint)

  def _get_headers(self):
    return {
        'Authorization': 'bearer {}'.format(self._get_authorization_token())}

  def _do_put(self, *args, **kwargs):
    kwargs['headers'] = self._get_headers()
    kwargs['print_curl'] = False
    return self._do_request(lambda: rrequests.put(*args, **kwargs))

  def _do_delete(self, *args, **kwargs):
    kwargs['headers'] = self._get_headers()
    return self._do_request(lambda: requests.delete(*args, **kwargs))

  def _do_request(self, closure):
    got = closure()
    raise_if_not_ok(got)
    return got

  def _get_authorization_token(self):
    return settings.TYPEFORM_SECRET
