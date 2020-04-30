""" This is pretty tiny at this point so it doesn't really deserve its own app.
"""
import requests
from requests.auth import HTTPBasicAuth

from django.conf import settings

from util.html_status_codes import NotOkError
from util.network import can_read_net


def is_voip(phone_number):
  return lookup(phone_number)['carrier']['type'] == 'voip'


def lookup(phone_number):
  if phone_number[0] != '+':
    raise Exception((
        'phone_number should be formatted, like, +16468671894, '
        'not {}').format(phone_number))
  got = _do_lookup(phone_number)
  if got.status_code == 200:
    """ For instance,
    {'caller_name': None,
     'country_code': 'US',
     'phone_number': '+16468671894',
     'national_format': '(646) 867-1894',
     'carrier': {'mobile_country_code': None,
      'mobile_network_code': None,
      'name': 'Twilio - Inteliquent - SMS-Sybase365/MMS-SVR',
      'type': 'voip',
      'error_code': None},
     'add_ons': None,
     'url': 'https://lookups.twilio.com/v1/PhoneNumbers/+16468671894?Type=carrier'} # noqa: E501
    """
    return got.json()
  if got.status_code == 404:
    """ For instance,
    {'code': 20404,
     'message': 'The requested resource /PhoneNumbers/asdf was not found',
     'more_info': 'https://www.twilio.com/docs/errors/20404',
     'status': 404}
    """
    raise NotOkError(got.status_code, got.json()['message'], got.url, {})
  raise Exception((
      'Not sure how to handle a response with status_code '
      '{} and content {}').format(got.status_code, got.content))


def _do_lookup(phone_number):
  if can_read_net():
    url = 'https://lookups.twilio.com/v1/PhoneNumbers/{}?Type=carrier'.format(
        phone_number)
    return requests.get(url, auth=HTTPBasicAuth(
        settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN))
