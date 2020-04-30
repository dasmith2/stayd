from json import JSONDecodeError, loads
import sys


class ServerError(Exception):
  pass


def raise_if_server_error(response, url=None, sent_data=None):
  if is_server_error(response):
    server_error = ServerError(
        response.status_code, response.content, url, sent_data)
    server_error.status_code = response.status_code
    server_error.content = response.content
    server_error.url = url
    raise server_error


class NotOkError(Exception):
  def __init__(self, status_code, content, url, sent_data):
    self.status_code = status_code
    self.content = content
    self.url = url
    self.sent_data = sent_data
    super().__init__(status_code, content, url, sent_data)

  def json(self):
    return loads(self.content.decode('utf-8'))


def raise_if_not_ok(response, url=None, sent_data=None):
  raise_if_server_error(response, url=url, sent_data=sent_data)
  if not is_ok(response):
    raise NotOkError(
        status_code=response.status_code, content=response.content, url=url,
        sent_data=sent_data)


def is_server_error(response):
  # (bad gateway, error, timeout)
  return response.status_code in (500, 502, 503, 504)


def is_ok(response):
  # 204 No Content. "The server has successfully fulfilled the request and
  # there is no additional content to send in the response payload body."
  return response.ok or response.status_code == 204


def get_json(response):
  if isinstance(response, dict):
    # This happens in tests.
    return response
  try:
    return response.json()
  except JSONDecodeError:
    from errors.models import log_error
    log_error(
        'Misunderstood json response', 'status code {}\n{}'.format(
            response.status_code, response.content), sys.exc_info())
