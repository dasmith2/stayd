"""
The Front API is documented at https://dev.frontapp.com/

Front is our front end for communicating with guests. It's a unified inbox.
It allows a team of people to pretend they're a single person (an avatar,
in other words) responding to any guest who replies to an email or SMS
that we sent via front.

Nothing in util should know about any business classes like reservations
or whatever. Front gets used by other classes.
"""

from collections import namedtuple
import re
import time

import requests
from django.conf import settings

from errors.models import log_error


class ContactInfo(
    namedtuple('ContactInfo', 'name description link phone email')):
  pass


class Front(object):
  headers = {
      'Authorization': 'Bearer {}'.format(settings.FRONT_JSON_WEB_TOKEN)}

  def _url(self, function_name):
    if function_name[0] == '/':
      function_name = function_name[1:]
    return 'https://api2.frontapp.com/{}'.format(function_name)

  def _get(self, function_name):
    return requests.get(self._url(function_name), headers=self.headers)

  def set_contact_infos(self, contact_info_list, verbose=False):
    """ By default, the API is limited to 120 requests in 60 seconds. If you
    need more, just ask us and we will consider raising your quota.

    When the rate limit is exceeded, the server will respond with a 429 Too
    Many Requests HTTP code with the header Retry-After to tell you how many
    seconds you need to wait before you can retry the request. """
    for contact_info in contact_info_list:
      if verbose:
        print(contact_info.name)
      self.set_contact_info(contact_info)
      time.sleep(1)

  def set_contact_info(self, contact_info, dont_do_it_in_dev=True):
    """ I just test this one manually. If you make any changes go run it
    in the shell.

    There's no obvious way to get a contact id given a
    phone number in the Front API. So. Just go ahead and try to make
    a new one. If it didn't exist yet, that will work, and we're done.
    If that phone number is already in there, you get a 409
    error code with an error message that says the contact id. THAT'S
    how you look up a contact id so you can PATCH an update. """
    if settings.DEBUG and dont_do_it_in_dev:
      return True
    new_data = {
        'name': contact_info.name,
        'description': contact_info.description,
        'links': [contact_info.link],
        'handles': [
            {'handle': contact_info.phone, 'source': 'phone'},
            {'handle': contact_info.email, 'source': 'email'}]}
    url = self._url('/contacts')
    first_save = requests.post(url, headers=self.headers, json=new_data)
    if first_save.ok:
      return True
    elif first_save.status_code == 429:
      log_error('Rate limiting on the front API')
      return False
    error_message = first_save.json()['_error']['message']
    message_finder = re.compile(r'crd_\w+')
    message_found = message_finder.search(error_message)
    if not message_found:
      log_error(
          'Couldn\'t find existing contact id in error message',
          'code: {}\n\nmessage: {}\n\ndata: {}'.format(
              first_save.status_code,
              error_message,
              new_data))
      return False
    contact_id = message_found.group()
    specific_url = self._url('/contacts/{}'.format(contact_id))
    loading_data = requests.get(specific_url, headers=self.headers)
    if loading_data.status_code == 429:
      log_error('Rate limiting on the front API')
      return False
    loaded_data = loading_data.json()
    loaded_data.update(new_data)
    patching = requests.patch(
        specific_url, headers=self.headers, json=loaded_data)
    if patching.status_code == 429:
      log_error('Rate limiting on the front API')
    return patching.ok and contact_id

  def get_channels(self):
    return self._get('/channels').json()['_results']

  def send_sms(self, to, content):
    from_channel = settings.FRONT_SMS_CHANNEL_ID
    url = self._url('/channels/{}/messages'.format(from_channel))
    data = {
        'body': content,
        'to': [to]}
    if settings.DEBUG:
      return True
    else:
      return requests.post(url, headers=self.headers, json=data).ok
