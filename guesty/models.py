from datetime import timedelta
import json

from django.db import models
from django.http import Http404
from django.utils import timezone

from guests.models import Guest
from guesty.api_getter import GuestyAPIGetter
from rentals.models import Rental
from reservations.models import Reservation


class RawEventManager(models.Manager):
  def rm_old(self, days_ago=31, verbose=False):
    when = timezone.now() - timedelta(days=days_ago)
    which = self.filter(created_at__lt=when)
    if verbose:
      print('Deleting {} raw events.'.format(which.count()))
    which.delete()


class RawEvent(models.Model):
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
          self.handled_at = timezone.now()
          self.is_404 = True
          self.save()
          return True
    return False


class GuestyRental(models.Model):
  rental = models.ForeignKey(Rental, on_delete=models.CASCADE)
  guesty_id = models.CharField(max_length=100)


class GuestyReservation(models.Model):
  reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE)
  guesty_id = models.CharField(max_length=100)


class GuestyGuest(models.Model):
  guest = models.ForeignKey(Guest, on_delete=models.CASCADE)
  guesty_id = models.CharField(max_length=100)
