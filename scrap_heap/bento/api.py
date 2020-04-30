from datetime import datetime
import requests
import time

from django.conf import settings

from util.html_status_codes import raise_if_server_error
from util.network import can_read_net


class API(object):
  """ https://apidocs.bentoforbusiness.com/ """
  def __init__(
      self, access_key=settings.BENTO_ACCESS_KEY,
      secret_key=settings.BENTO_SECRET_KEY):
    self.authorization_token = None
    self.access_key = access_key
    self.secret_key = secret_key

  def list_cards(self):
    return self._do_get('/cards')

  def get_transaction(self, transaction_id):
    url = '/transactions/{}'.format(transaction_id)
    return self._fix_transaction(self._do_get(url).json())

  def list_transactions(self, date_start=None, date_end=None, card_ids=[]):
    """ card_ids could be, for instance,
    [str(card['cardId']) for card in api.list_cards().json()] """
    url = '/transactions'
    params = {}
    if date_start:
      params['dateStart'] = self._date_to_int64(date_start)
    if date_end:
      params['dateEnd'] = self._date_to_int64(date_end)
    if card_ids:
      str_card_ids = [str(card_id) for card_id in card_ids]
      params['cards'] = ','.join(str_card_ids)
    transactions = self._do_get(url, params).json()['cardTransactions']
    for transaction_dict in transactions:
      self._fix_transaction(transaction_dict)
    return transactions

  def _fix_transaction(self, transaction_dict):
    transaction_dict['transactionDate'] = self._int64_to_datetime(
        transaction_dict['transactionDate'])
    transaction_dict['settlementDate'] = self._int64_to_datetime(
        transaction_dict['settlementDate'])
    return transaction_dict

  def _date_to_int64(self, date_):
    return int(time.mktime(date_.timetuple())) * 1000

  def _int64_to_datetime(self, ts):
    return datetime.fromtimestamp(ts / 1000)

  def _do_get(self, endpoint, params={}):
    if can_read_net():
      got = requests.get(
          self._bento_url(endpoint), params=params,
          headers=self._get_headers())
      raise_if_server_error(got)
      return got

  def _get_headers(self):
    return {'Authorization': self._get_authorization_token()}

  def _get_authorization_token(self):
    if not self.authorization_token:
      got = self._do_authorization_token_get()
      self.authorization_token = got.headers['Authorization']
    return self.authorization_token

  def _do_authorization_token_get(self):
    return requests.post(self._bento_url('/sessions'), json={
        'accessKey': self.access_key,
        'secretKey': self.secret_key})

  def _bento_url(self, endpoint):
    if endpoint and endpoint[0] == '/':
      endpoint = endpoint[1:]
    return '{}/{}'.format(settings.BENTO_API_ROOT, endpoint)
