import json as json_the_library

import requests


def post_curl_command(url, headers, json):
  return ''.join([
      'curl --header "Content-Type: application/json" \\\n',
      _curl_headers(headers),
      '     --request POST \\\n',
      '     --data \'{}\' \\\n'.format(json_the_library.dumps(json)),
      '     {}'.format(url)])


def post(url, headers={}, json={}, print_curl=False):
  if print_curl:
    print(post_curl_command(url, headers, json))
  return requests.post(url, headers=headers, json=json)


def get_curl_command(url, headers):
  return ''.join([
      'curl ',
      _curl_headers(headers),
      '     --request GET \\\n',
      '     {}'.format(url)])


def get(url, headers=None, print_curl=False):
  if print_curl:
    print(get_curl_command(url, headers))
  return requests.get(url, headers=headers)


def delete(url, headers=None):
  return requests.delete(url, headers=headers)


def put_curl_command(url, headers, json):
  return ''.join([
      'curl --header "Content-Type: application/json" \\\n',
      _curl_headers(headers),
      '     --request PUT \\\n',
      '     --data \'{}\' \\\n'.format(json_the_library.dumps(json)),
      '     --url {}'.format(url)])


def put(url, headers=[], json={}, print_curl=False):
  if print_curl:
    print(put_curl_command(url, headers, json))
  return requests.put(url, headers=headers, json=json)


def _curl_headers(headers):
  if headers:
    parts = []
    for key, value in headers.items():
      parts.append('     --header "{}: {}" \\\n'.format(key, value))
    return ''.join(parts)
  return ''
