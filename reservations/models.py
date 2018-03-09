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
      max_digits=10, decimal_places=2, default_currency='USD', help_text=(
          'Total amount that landed in our bank account due to this '
          'reservation. It\'s not cost, excactly, because it reflects things '
          'like Airbnb\'s service fee which comes out of our hides. Airbnb '
          'calls this total_payout for obvious reasons.'))
  is_paid_in = models.BooleanField(default=False, help_text=(
      'Whether or not this reservation is in the Airbnb list of '
      'transaction, a.k.a. mama got paid.'))


class ReservationPayinItem(models.Model):
  """ Line items that add up to a reservation's total_payin. For instance,
  there could be Rent which is price_per_night * night_count, the Airbnb
  service fee which will be negative, and a cleaning charge. """
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
