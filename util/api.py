from django.conf import settings
import requests
from requests.auth import HTTPBasicAuth


def get(api_urls_name, **api_urls_kwargs):
  return requests.get(
      _get_url(api_urls_name, **api_urls_kwargs),
      auth=_get_auth())


def post(api_urls_name, data_dict):
  return requests.post(
      _get_url(api_urls_name, **api_urls_kwargs),
      json=data_dict,
      auth=_get_auth())


def _get_auth():
  return HTTPBasicAuth(settings.STAYD_API_USER, settings.STAYD_API_PASSWORD)


def _get_url(api_urls_name, **api_urls_kwargs):
  return reverse(api_urls_name, **api_urls_kwargs)
