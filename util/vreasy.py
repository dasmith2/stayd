from django.conf import settings
import requests
from reservations.serializers import ReservationSerializer
from reservations.models import Reservation

# From vreasy.com/docs/public-api/
# "use the api-key as the username with no password"
auth = (settings.VREASY_API_KEY, '')


class vreasy(object):
  def api_url(self, action_path):
    if action_path[0] == '/':
      action_path = action_path[1:]
    return 'https://www.vreasy.com/api/' + action_path

  def get_listings(self):
    return requests.get(self.api_url('listings'), auth=auth)

  def get_reservations(self):
    return requests.get(self.api_url('reservations'), auth=auth)

  def get_channels(self):
    return requests.get(self.api_url('reservations'), auth=auth)

  def _strip_empty(self, got):
    del_keys = []
    for key in got.keys():
      if not got[key]:
        del_keys.append(key)
    for key in del_keys:
      del got[key]
    return got

  def get_from_vreasy(self):
    url = self.api_url('reservations?portal_uid=HMCTDKY9H8')
    return self._strip_empty(requests.get(url).json()[0])

  def get_from_me(self):
    return ReservationSerializer(
        Reservation.objects.get(
            channel_reservation_id='HMCTDKY9H8')).data
