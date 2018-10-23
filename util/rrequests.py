import json as json_the_library

import requests


def post_curl_command(url, headers, json):
  command = (
      'curl --header "Content-Type: application/json" \\\n')
  for key, value in headers.items():
    command += ('     --header "{}: {}" \\\n').format(key, value)
  command += (
      '     --request POST \\\n'
      '     --json \'{}\' \\\n'
      '     {}').format(json_the_library.dumps(json), url)
  return command


def post(url, headers=[], json={}, print_curl=False):
  if print_curl:
    print(post_curl_command(url, headers, json))
  return requests.post(url, headers=headers, json=json)
