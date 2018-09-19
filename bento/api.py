import requests

from django.conf import settings


class API(object):
  def __init__(self):
    self.authorization_token = None

  def list_cards(self, ok_to_do_it_in_dev=False):
    return self._do_get('/cards', ok_to_do_it_in_dev)

  def _do_get(self, endpoint, ok_to_do_it_in_dev=False):
    if ok_to_do_it_in_dev or (settings.PROD and settings.BACKGROUND):
      return requests.get(
          self._bento_url(endpoint), headers=self._get_headers())
    else:
      raise Exception(
          'The Bento API is being called from an innapropriate environment!')

  def _get_headers(self):
    return {'Authorization': self._get_authorization_token()}

  def _get_authorization_token(self):
    if not self.authorization_token:
      got = requests.post(self._bento_url('/sessions'), json={
          'accessKey': settings.BENTO_ACCESS_KEY,
          'secretKey': settings.BENTO_SECRET_KEY})
      self.authorization_token = got.headers['Authorization']
    return self.authorization_token

  def _bento_url(self, endpoint):
    if endpoint and endpoint[0] == '/':
      endpoint = endpoint[1:]
    return '{}/{}'.format(settings.BENTO_API_ROOT, endpoint)
