from datetime import timedelta
import json

from django.db import models
from django.http import Http404
from django.utils.timezone import now

from guesty.custom_fields import CustomFields
from guests.models import Guest
from guesty.api_getter import GuestyAPIGetter
from rentals.models import Rental
from reservations.models import Reservation


class RawEventManager(models.Manager):
  def rm_old(self, days_ago=31, verbose=False):
    """ Basically an exact copy of
    guest_messages.models.RawMandrillEventManager.rm_old """
    when = now() - timedelta(days=days_ago)
    which = self.filter(created_at__lt=when)
    if verbose:
      print('Deleting {} raw events.'.format(which.count()))
    which.delete()


class RawEvent(models.Model):
  """ Not unlike guest_messages.models.RawMandrillEvent """
  json = models.TextField(help_text='The raw json string from the request.')
  event_name = models.CharField(max_length=100)
  created_at = models.DateTimeField(auto_now_add=True, db_index=True)
  handled_at = models.DateTimeField(null=True, blank=True)
  reservation = models.ForeignKey(
      Reservation, null=True, blank=True, on_delete=models.CASCADE)
  is_404 = models.BooleanField(default=False)

  objects = RawEventManager()

  def check_404_reservation(self, getter=GuestyAPIGetter()):
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


class GuestyRental(models.Model):
  rental = models.OneToOneField(Rental, on_delete=models.CASCADE)
  guesty_id = models.CharField(max_length=100, db_index=True)


class GuestyReservationManager(models.Manager):
  def admin_url(self, guesty_id):
    return 'https://app.guesty.com/reservations/{}/guests'.format(guesty_id)


class GuestyReservation(models.Model):
  reservation = models.OneToOneField(Reservation, on_delete=models.CASCADE)
  guesty_id = models.CharField(max_length=100, db_index=True)

  objects = GuestyReservationManager()

  def admin_url(self):
    return GuestyReservation.objects.admin_url(self.guesty_id)

  def get_custom_fields(self, api_getter=None):
    from guesty.api import GuestyAPIGetter
    if not api_getter:
      api_getter = GuestyAPIGetter()
    custom_fields_json = api_getter.get_one(
        Reservation, self.guesty_id)['customFields']
    return CustomFields(Reservation, self.guesty_id, custom_fields_json)


class GuestyGuest(models.Model):
  guest = models.OneToOneField(Guest, on_delete=models.CASCADE)
  guesty_id = models.CharField(max_length=100, db_index=True)
