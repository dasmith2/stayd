from django.db import models
from djmoney.models.fields import MoneyField

from guests.models import Guest
from listings.models import Listing
from pays.models import Payin


class Reservation(models.Model):
  channel_reservation_id = models.CharField(max_length=50, help_text=(
      'The id given to this reservation by Airbnb, booking.com, or whomever.'))
  guest = models.ForeignKey(Guest, on_delete=models.CASCADE)
  check_in = models.DateTimeField()
  check_out = models.DateTimeField()
  listing = models.ForeignKey(Listing, on_delete=models.CASCADE)
  price_per_night = MoneyField(
      max_digits=10, decimal_places=2, default_currency='USD')
  night_count = models.PositiveIntegerField(help_text=(
      'How many nights did they stay? We could calculate this from check_in '
      'and check_out, but humor me. This will make reports easier to write.'))
  total_payin = MoneyField(
      max_digits=10, decimal_places=2, default_currency='USD')


class ReservationLineItem(models.Model):
  name = models.TextField()
  value = MoneyField(
      max_digits=10, decimal_places=2, default_currency='USD')
  reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE)


class ReservationToPayin(models.Model):
  """ You can receive multiple payins for the same reservation. You can also
  get paid for multiple reservations on the same payin. I've never seen it
  where you have two reservations, each related to two payins, but I wouldn't
  be surprised.
  """
  reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE)
  payin = models.ForeignKey(Payin, on_delete=models.CASCADE)
