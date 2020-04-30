from datetime import datetime
import json

from django.db import models
from django.http import Http404
from util.timezone import now

from guesty.custom_fields import CustomFields
from guests.models import Guest
from guesty.api import GuestyAPI
from rentals.models import Rental
from reservations.models import Reservation
from util.fields import OneToOneOrNoneField
from util.rm_old import RmOldManager
from util.webhook import Webhook


class ReservedReservation(models.Model):
  """ The whole point of this class is to keep track of "reserved"
  reservations. "reserved" reservations can transition to "closed", "declined",
  or "confirmed". Guesty is failing to send a webhook on the transition to
  "confirmed" (at least) so, jeeze, I guess we poll. """
  guesty_id = models.CharField(max_length=100)
  created_at = models.DateTimeField(auto_now_add=True, db_index=True)


class RawEvent(Webhook):
  """ Not unlike guest_messages.models.RawMandrillEvent """
  event_name = models.CharField(max_length=100)
  reservation = models.ForeignKey(
      Reservation, null=True, blank=True, on_delete=models.CASCADE)
  is_404 = models.BooleanField(default=False)

  objects = RmOldManager()

  def check_404_reservation(self, getter=GuestyAPI()):
    """ Yeah, one time I got a webhook for a reservation that didn't exist.
    But the json in that webhook was filled out enough that it got pretty far
    into it before things went wrong. Specifically, there was no guest
    information. """
    if self.event_name.find('reservation') >= 0:
      request_data = json.loads(self.json)
      if 'reservation' in request_data:
        r_long = request_data['reservation']
        try:
          getter.get_one(Reservation, r_long['_id'])
        except Http404:
          self.handled_at = now()
          self.is_404 = True
          self.save()
          return True
    return False

  class Meta:
    ordering = ('-created_at',)


BOOKED = 'booked'
UNAVAILABLE = 'unavailable'
AVAILABLE = 'available'


class GuestyRental(models.Model):
  rental = OneToOneOrNoneField(Rental, on_delete=models.CASCADE)
  guesty_id = models.CharField(max_length=100, db_index=True, unique=True)

  def block(self, night, reason, api=None):
    api = api or GuestyAPI()
    if isinstance(night, datetime):
      night = night.date()
    api.block(self.guesty_id, night, reason)

  def unblock(self, night, api=None):
    api = api or GuestyAPI()
    if isinstance(night, datetime):
      night = night.date()
    api.unblock(self.guesty_id, night)

  def is_blocked(self, night, api=None):
    return self.get_availability(night, api) == 'unavailable'

  def get_availability(self, night, api=None):
    api = api or GuestyAPI()
    if isinstance(night, datetime):
      night = night.date()
    got_json = api.get_calendar(self.guesty_id, night, night)
    return got_json[0]['status']  # booked, unavailable, available

  def sync(self):
    from guesty.guesty import Guesty
    sync = Guesty()
    sync.sync_rental(sync.api.get_one(Rental, self.guesty_id))

  def turn_on_all_messages(self, api=None):
    api = api or GuestyAPI()
    for reservation in Reservation.objects.filter(rental=self.rental):
      custom_fields = reservation.guestyreservation.get_custom_fields(api)
      custom_fields.turn_on_for_imported_reservation(api)


class GuestyReservationManager(models.Manager):
  def admin_url(self, guesty_id):
    return 'https://app.guesty.com/reservations/{}/guests'.format(guesty_id)


class GuestyReservation(models.Model):
  reservation = OneToOneOrNoneField(Reservation, on_delete=models.CASCADE)
  guesty_id = models.CharField(max_length=100, db_index=True, unique=True)

  objects = GuestyReservationManager()

  def admin_url(self):
    return GuestyReservation.objects.admin_url(self.guesty_id)

  def get_custom_fields(self, api=None):
    from guesty.guesty import GuestyAPI
    if not api:
      api = GuestyAPI()
    custom_fields_json = api.get_one(
        Reservation, self.guesty_id)['customFields']
    return CustomFields(Reservation, self.guesty_id, custom_fields_json)


class GuestyGuest(models.Model):
  guest = OneToOneOrNoneField(Guest, on_delete=models.CASCADE)
  guesty_id = models.CharField(max_length=100, db_index=True)
