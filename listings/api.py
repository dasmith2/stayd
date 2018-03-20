from django.utils.text import slugify

from util import api


class AirvatarAPI(object):
  def all(self):
    return [Airvatar(**a) for a in api.get('list-airvatars-api').json()]

  def get(self, name):
    return api.get('retrieve-airvatar-api', name_slug=slugify(name)).json()