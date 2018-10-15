import requests

from django.conf import settings


class API(object):
  """ https://apidocs.bentoforbusiness.com/ """
  def __init__(self):
    self.authorization_token = None

  def list_cards(self, ok_to_do_it_in_dev=False):
    return self._do_get('/cards', ok_to_do_it_in_dev)

  def list_transactions(self, card_ids=[], ok_to_do_it_in_dev=False):
    """ card_ids could be, for instance,
    [str(card['cardId']) for card in api.list_cards().json()] """
    url = '/transactions'
    if card_ids:
      str_card_ids = [str(card_id) for card_id in card_ids]
      url += '?cards={}'.format(','.join(str_card_ids))
    return self._do_get(url, ok_to_do_it_in_dev)

  def _do_get(self, endpoint, ok_to_do_it_in_dev=False):
    if ok_to_do_it_in_dev or (
        settings.PROD and settings.BACKGROUND) or settings.SHELL:
      return requests.get(
          self._bento_url(endpoint), headers=self._get_headers())
    else:
      raise Exception(
          'The Bento API is being called from an innapropriate environment!')

  def _get_headers(self):
    return {'Authorization': self._get_authorization_token()}

  def _get_authorization_token(self):
    if not self.authorization_token:
      got = self._do_authorization_token_get()
      self.authorization_token = got.headers['Authorization']
    return self.authorization_token

  def _do_authorization_token_get(self):
    return requests.post(self._bento_url('/sessions'), json={
        'accessKey': settings.BENTO_ACCESS_KEY,
        'secretKey': settings.BENTO_SECRET_KEY})

  def _bento_url(self, endpoint):
    if endpoint and endpoint[0] == '/':
      endpoint = endpoint[1:]
    return '{}/{}'.format(settings.BENTO_API_ROOT, endpoint)
