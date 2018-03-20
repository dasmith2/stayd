from django.utils.text import slugify

from listings.models import Airvatar
from util import api


class AirvatarAPI(object):
  def all(self):
    return [Airvatar(**a) for a in api.get('list-airvatars-api').json()]

  def get(self, name):
    got = api.get('retrieve-airvatar-api', name_slug=slugify(name))
    if not got.ok:
      got.raise_for_status()
    return Airvatar(**got.json())
