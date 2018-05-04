from django.db import models

from guests.models import Guest
from rentals.models import Rental
from reservations.models import Reservation


class RawEvent(models.Model):
  json = models.TextField(help_text='The raw json string from the request.')
  headers = models.TextField()


class GuestyRental(models.Model):
  rental = models.ForeignKey(Rental, on_delete=models.CASCADE)
  guesty_id = models.CharField(max_length=100)


class GuestyReservation(models.Model):
  reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE)
  guesty_id = models.CharField(max_length=100)


class GuestyGuest(models.Model):
  guest = models.ForeignKey(Guest, on_delete=models.CASCADE)
  guesty_id = models.CharField(max_length=100)
