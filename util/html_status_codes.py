from json import JSONDecodeError
import sys


def is_server_error(response):
  # (bad gateway, error, timeout)
  return response.status_code in (500, 502, 503, 504)


def is_ok(response):
  # 204 No Content. "The server has successfully fulfilled the request and
  # there is no additional content to send in the response payload body."
  return response.ok or response.status_code == 204


def get_json(response):
  try:
    return response.json()
  except JSONDecodeError:
    from errors.models import log_error
    log_error(
        'Misunderstood json response', 'status code {}\n{}'.format(
            response.status_code, response.content), sys.exc_info())
