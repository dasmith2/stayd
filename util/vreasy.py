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

  def g(self, url):
    return requests.get(self.api_url(url), auth=auth).json()

  def gs(self, url):
    return requests.get(self.api_url(url), auth=auth).json()

  def st(self, got):
    del_keys = []
    for key in got.keys():
      if not got[key]:
        del_keys.append(key)
    for key in del_keys:
      del got[key]
    return got

  def get_from_vreasy(self):
    return self.st(self.g('reservations?portal_uid=HMCTDKY9H8')[0])

  def get_from_me(self):
    return ReservationSerializer(
        Reservation.objects.get(
            channel_reservation_id='HMCTDKY9H8')).data

  def wah(self):
    e = open('endpoints.txt', 'w')
    endpoints = [
        'account', 'brandings', 'calendars', 'channels', 'channel-credentials',
        'channel-commissions', 'currencies', 'expenses', 'keys', 'listings',
        'payments', 'properties', 'rates', 'reservations', 'subscriptions',
        'users']
    for point in endpoints:
      got = requests.get(self.api_url(point), auth=auth).json()
      if got.__class__ is [].__class__ and len(got) > 0:
        got = got[int(len(got) / 2)]
      if got.__class__ is {}.__class__:
        self.st(got)
        if got.get('message', '') == 'Page not found':
          got = '404'
      print(point)
      print(got)
      e.write('{}\n\n{}\n\n'.format(point, got))

  """
  RESVS = 'reservations?start=2018-03-18T15:00:00-04:00'
  /account current logged in user
  /ammenities
  /brandings
  /calendars
    id - reservation id
    property_ids - []
    status - CONFIRMED
    start, end - 2015-01-10T09:30:47+02:00
    portal_uid
    https://www.vreasy.com/docs/public-api/#!/Calendars/get_calendars
    responds with listing_id, portal_uid, status, checkin, and checkout
  /channels
  /channel-credentials
  objs = ['accounts', 'channels']
  """
