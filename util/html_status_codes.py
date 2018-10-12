def is_server_error(response):
  # (bad gateway, error, timeout)
  return response.status_code in (500, 502, 503, 504)


def is_ok(response):
  # 204 No Content. "The server has successfully fulfilled the request and
  # there is no additional content to send in the response payload body."
  return response.ok or response.status_code == 204
