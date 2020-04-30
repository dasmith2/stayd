"""
https://developer.aircall.io/api-references/
"""
import time

from django.conf import settings

from util.network import can_read_net, can_write_net
from util import rrequests
from util.html_status_codes import raise_if_not_ok


class API(object):
  def get_contact(self, phone_number):
    endpoint = 'contacts/search?phone_number={}'.format(phone_number)
    contacts = self._get(endpoint).json()['contacts']
    # Aircall doesn't appear to actually delete contacts. Also at first I saved
    # these with phone number type of 'Phone' but then it seemed that Aircall
    # was making copies of the exact same contact with everything the same
    # except the type turned to 'work'. So delete the duplicates here and
    # update any 'Phone' types to 'work'.
    for contact in contacts[1:]:
      self.delete_contact(contact['id'])  # Pretty sure this does nothing.
    if len(contacts):
      contact = contacts[0]
      phone_data = contact['phone_numbers'][0]
      if phone_data['label'] == 'Phone':
        contact['phone_numbers'] = [
            {'label': 'work', 'value': phone_data['value']}]
        self.save_contact(contact)
      return contact

  def delete_contact(self, contact_id):
    endpoint = 'contacts/{}'.format(contact_id)
    return self._delete(endpoint)

  def save_contact(self, data, print_curl=False):
    endpoint = 'contacts'
    if data.get('id', None):
      endpoint += '/{}'.format(data['id'])
    return self._post(endpoint, data, print_curl=print_curl)

  def get_contacts(self, next_url=None):
    next_url = next_url or 'contacts'
    while next_url:
      print(next_url)
      got = self._get(next_url).json()
      for contact in got['contacts']:
        yield contact
      next_url = got['meta'].get('next_page_link')

  def ping(self):
    return self._get('ping')

  def _url(self, endpoint):
    desired_root = 'https://{}:{}@api.aircall.io/v1/'.format(
        settings.AIRCALL_API_ID, settings.AIRCALL_API_TOKEN)
    endpoint = endpoint.replace('https://api.aircall.io/v1/', desired_root)
    if endpoint.find(desired_root) == -1:
      if endpoint[0] == '/':
        endpoint = endpoint[:-1]
      return '{}{}'.format(desired_root, endpoint)
    return endpoint

  def _post(self, endpoint, data, print_curl=False):
    if can_write_net():
      url = self._url(endpoint)

      def closure():
        return rrequests.post(url, json=data, print_curl=print_curl)
      return self._do_request(closure, url=url, sent_data=data)

  def _get(self, endpoint, print_curl=False):
    if can_read_net():
      url = self._url(endpoint)

      def closure():
        return rrequests.get(url, print_curl=print_curl)
      return self._do_request(closure, url=url)

  def _delete(self, endpoint):
    if can_write_net():
      url = self._url(endpoint)

      def closure():
        return rrequests.delete(url)
      return self._do_request(closure, url=url)

  def _do_request(self, closure, url=None, sent_data=None):
    """ This API is limited to 60 requests in 60 seconds. Aircall says it'll
    send along headers explaining when you can begin making calls again, but
    they don't. So we'll just do exponential backoff. """
    response = closure()
    attempts = 0
    while response.status_code == 403 and attempts < 5:
      time.sleep(5 ** attempts)
      response = closure()
      attempts += 1
    raise_if_not_ok(response, url=url, sent_data=sent_data)
    return response
