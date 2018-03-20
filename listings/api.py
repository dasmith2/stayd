from util import api


class AirvatarAPI(object):
  def all(self):
    return api.get('list-airvatars-api').json()
