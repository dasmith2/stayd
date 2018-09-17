def is_server_error(response):
  # (bad gateway, error, timeout)
  return response.status_code in (502, 503, 504)
