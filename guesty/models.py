from datetime import timedelta

from django.db import models
from django.utils import timezone

from guests.models import Guest
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
  handled = models.BooleanField(default=False)

  objects = RawEventManager()


class GuestyRental(models.Model):
  rental = models.ForeignKey(Rental, on_delete=models.CASCADE)
  guesty_id = models.CharField(max_length=100)


class GuestyReservation(models.Model):
  reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE)
  guesty_id = models.CharField(max_length=100)


class GuestyGuest(models.Model):
  guest = models.ForeignKey(Guest, on_delete=models.CASCADE)
  guesty_id = models.CharField(max_length=100)
