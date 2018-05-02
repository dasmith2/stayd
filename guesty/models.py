from django.db import models

from guests.models import Guest
from rentals.models import Rental
from reservations.models import Reservation


class GuestyRental(models.Model):
  rental = models.ForeignKey(Rental, on_delete=models.CASCADE)
  guesty_id = models.CharField(max_length=100)


class GuestyReservation(models.Model):
  reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE)
  guesty_id = models.CharField(max_length=100)


class GuestyGuest(models.Model):
  guest = models.ForeignKey(Guest, on_delete=models.CASCADE)
  guesty_id = models.CharField(max_length=100)
