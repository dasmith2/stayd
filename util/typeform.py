from django.conf import settings
import requests

"""
For the Create and Responses APIs, you can send two requests per second, per
Typeform account.
"""
TYPEFORM_BASE_URL = ''


def responses_url(form_id):
  return 'https://api.typeform.com/forms/{}/responses'.format(form_id)


def typeform_headers():
  return {
      'authorization': 'bearer {}'.format(settings.TYPEFORM_ACCESS_TOKEN)}


def get_responses(form_id='Y3Fpua'):
  url = responses_url(form_id)
  # This is great and all, but you can't download image submissions.
  # I ran into that dead and and confirmed it with TypeForm support.
  return requests.get(url, headers=typeform_headers())
