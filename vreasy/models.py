from django.conf import settings
from django.db import models
from django.utils.dateparse import parse_datetime
from django.utils.timezone import make_aware

from guests.models import Guest
from rentals.models import Rental
from reservations.models import Reservation
from vreasy.api import VreasyAPI
from util.channels import AIRBNB
from util.error_reporting import resolve_me


class RawEvent(models.Model):
  """
  Vreasy has webhooks. I don't have them integrated yet because
  reservations seem to only 404 so far. But when the time comes,
  store them here so we can get a handle on them.
  """
  json = models.TextField(help_text='The raw json string from the request.')
  headers = models.TextField(help_text='')


class VreasyProperty(models.Model):
  vreasy_id = models.PositiveIntegerField(help_text=(
      'The id assigned by vreasy.'))
  title = models.CharField(max_length=200, help_text=(
      'The title from Vreasy. Don\'t edit this.'))
  rental = models.ForeignKey(Rental, blank=True, null=True, help_text=(
      'What rental of ours is this talking about?'), on_delete=models.CASCADE)

  def __str__(self):
    return self.title


class VreasyLoader(object):
  def __init__(self, vreasy_api):
    self.vreasy_api = vreasy_api

  def pull_properties(self):
    for property in self.vreasy_api.get_properties():
      VreasyProperty.objects.get_or_create(
          vreasy_id=property['id'], title=property['title'])

  def pull_recent_reservations(self):
    reservations = []
    for res_json in self.vreasy_api.get_recently_modified_reservations():
      # Figure out why accommodation_cost is blank sometimes, like for the
      # reservation with portal_uid HMNTH9WCTC
      accommodation_cost = res_json.get('accommodation_cost', None)
      checkin = res_json.get('checkin', None)
      checkout = res_json.get('checkout', None)
      created_at = res_json.get('created_at', None)
      guest = res_json.get('guest', None)
      portal_uid = res_json.get('portal_uid', None)
      currency_id = res_json.get('currency_id', None)
      if not currency_id == 2:
        resolve_me(
            'A Vreasy reservation was paid in something besides US currency', (
            'from vreasy.api import VreasyAPI\n'
            '[c for c in VreasyAPI().get(\'currencies\').json() if '
            'c[\'id\'] == {}]').format(currency_id))
        continue
      listing = self._listing_from_property_id(property_id)
      if all([
          accommodation_cost, checkin, checkout, created_at, guest,
          portal_uid, listing]):
        reservations = Reservation.objects.filter(
            channel_reservation_id=channel_reservation_id)
        if reservations:
          res = reservations[0]
        else:
          res = Reservation(channel_reservation_id=channel_reservation_id)
        res.total_payin = Money(accommodation_cost, 'USD')
        res.check_in = parse_datetime(checkin)
        res.check_out = parse_datetime(checkout)
        res.reservation_created = make_aware(parse_datetime(created_at))
        res.guest = self._guest_from_json(guest)
        res.channel_reservation_id = portal_uid
        res.listing = listing
        res.save()
        reservations.append(res)
    return reservations

  def _guest_from_json(self, guest_json):
    full_name = guest_json['full_name']
    phone = guest_json.get('phone', None)
    numbers_only_phone = None
    if phone:
      numbers_only_phone = GuestPhoneNumber.objects.numbers_only(phone)
    vreasy_id = guest_json['guest_id']

    guests = Guest.objects.filter(vreasy_id=vreasy_id)
    if guests:
      guest = guests[0]
    else:
      guests = GuestPhoneNumber.objects.filter(
          numbers_only=numbers_only_phone, guest__full_name=full_name)
      if guests:
        guest = guests[0]
      else:
        guest = Guest.objects.create(
            full_name=full_name, phone=phone)
    GuestPhoneNumber.objects.create_for_guest(guest)
    return guest

  def _listing_from_property_id(self, property_id):
    properties_admin_url = '{}/admin/vreasy/vreasyproperty/'.format(
        settings.THIS_SERVERS_BASE_URL)
    vreasy_properties = VreasyProperty.objects.filter(vreasy_id=property_id)
    if not vreasy_properties:
      resolve_me(
          'Missing VreasyProperty', (
              'We need to run `python manage.py vreasy properties` to get '
              'a VreasyProperty with vreasy_id = {}. Then we need to '
              'link that to a Rental on {}').format(
                  property_id, properties_admin_url))
      return
    vreasy_property = vreasy_properties[0]
    if not vreasy_property.rental:
      resolve_me(
          'A VreasyProperty doesn\'t have a Rental', (
          'VreasyProperty with id {} and title {} needs to be linked to '
          'a Rental on {}').format(
              vreasy_property.vreasy_id, vreasy_property.title,
              properties_admin_url))
      return
    listings = Listing.objects.filter(channel=AIRBNB, rental=rental)
    if not listings:
      resolve_me(
          'A Rental doesn\'t have an AIRBNB Listing',
          '{}'.format(rental))
      return
    return listings[0]
