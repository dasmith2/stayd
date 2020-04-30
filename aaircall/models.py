"""
There are duplicates of basically every aircall contact because, I believe, the
API doesn't actually let you delete contacts and when I first did this project
I accidentally copied over all the front contacts without phones.

'phone_numbers': [{'label': 'work', 'value': phone_number}],
instead of
'phone_numbers': [phone_number]
You know? Classic mistake.

I should have updated the existing contacts instead of deleting and resaving
them. Now forever there are lots of duplicates.
"""
from datetime import timedelta

from aaircall.api import API
from commands.models import background_command
from front.api import FrontAPI
from util.html_status_codes import NotOkError, ServerError
from util.phone import looks_like_phone_number, maybe_prepend_plus
from util.timezone import now, ts_to_utc_dt


@background_command
def push_front_contacts_to_aircall_background():
  push_front_contacts_to_aaircall(modified_since=now() - timedelta(days=3))


def push_front_contacts_to_aaircall(
    api=None, front_api=None, modified_since=None, next_get_contacts_url=None):
  front_api = front_api or FrontAPI()
  api = api or API()
  for front_data in front_api.get_contacts(next_url=next_get_contacts_url):
    if modified_since and ts_to_utc_dt(
        front_data['updated_at']) < modified_since:
      return
    try:
      push_front_contact_to_aaircall(front_data, api)
    except ServerError:
      pass  # NBD, it'll probably get through the next time.


def push_front_contact_to_aaircall(front_data, api):
  aaircall_data = front_contact_data_to_aaircal_contact_data(front_data)
  if aaircall_data:
    phone_number = aaircall_data['phone_numbers'][0]['value']
    existing = api.get_contact(phone_number)
    if existing:
      aaircall_data['id'] = existing['id']
      names_equal = (
          existing.get('first_name', '') == aaircall_data['first_name'])
      info_equal = (
          existing.get('information', '') == aaircall_data['information'])
      if names_equal and info_equal:
        return
    try:
      api.save_contact(aaircall_data).json()
    except NotOkError as ex:
      if ex.json().get('troubleshoot', '') != (
          'Phone numbers are not all valid'):
        raise ex


def front_contact_data_to_aaircal_contact_data(front_data):
  phone_number = None
  for handle in front_data.get('handles', []):
    if handle['source'] == 'phone':
      # One time, Front had a contact with a phone handle of "romy"
      if looks_like_phone_number(handle['handle']):
        phone_number = maybe_prepend_plus(handle['handle'])
  if phone_number:
    link = None
    links = front_data.get('links', [])
    if links:
      link = links[0]
    description = '\n'.join(filter(
        None, [front_data.get('description', None), link]))
    return {
        'first_name': front_data['name'],
        'phone_numbers': [{'label': 'work', 'value': phone_number}],
        'information': description}


def delete_contacts_without_phone_numbers(next_get_contacts_url=None):
  api = API()
  for contact in api.get_contacts(next_url=next_get_contacts_url):
    if not len(contact.get('phone_numbers', [])):
      api.delete_contact(contact['id'])
