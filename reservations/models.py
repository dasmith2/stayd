from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver
from djmoney.models.fields import MoneyField

from guests.models import Guest
from listings.models import Listing
from pays.models import Payin


class Reservation(models.Model):
  channel_reservation_id = models.CharField(
      db_index=True, max_length=50, help_text=(
          'The id given to this reservation by Airbnb, booking.com, '
          'or whomever.'))
  guest = models.ForeignKey(Guest, on_delete=models.CASCADE)
  check_in = models.DateTimeField()
  check_out = models.DateTimeField()
  listing = models.ForeignKey(Listing, on_delete=models.CASCADE, null=False)
  # Default currency is useless. It will use XYZ if you don't specify.
  price_per_night = MoneyField(
      max_digits=10, decimal_places=2, default_currency='XYZ')
  night_count = models.PositiveIntegerField(help_text=(
      'How many nights did they stay? We could calculate this from check_in '
      'and check_out, but humor me. This will make reports easier to write.'))
  # Default currency is useless. It will use XYZ if you don't specify.
  total_payin = MoneyField(
      max_digits=10, decimal_places=2, default_currency='XYZ', help_text=(
          'Total amount that landed in our bank account due to this '
          'reservation. It\'s not cost, excactly, because it reflects things '
          'like Airbnb\'s service fee which comes out of our hides. Airbnb '
          'calls this total_payout for obvious reasons.'))
  is_paid_in = models.BooleanField(default=False, help_text=(
      'Whether or not this reservation is in the Airbnb list of '
      'transaction, a.k.a. mama got paid.'))

  def line_items(self):
    return ReservationLineItem.objects.filter(reservation=self)

  @receiver(pre_save)
  def pre_save(sender, instance, *args, **kwargs):
    if instance.__class__ is Reservation:
      rental = instance.listing.rental
      instance.check_in = rental.set_timezone(instance.check_in)
      instance.check_out = rental.set_timezone(instance.check_out)
      instance.price_per_night = rental.set_currency(instance.price_per_night)
      instance.total_payin = rental.set_currency(instance.total_payin)


class ReservationLineItem(models.Model):
  """ Line items that add up to a reservation's total_payin. For instance,
  there could be Rent which is price_per_night * night_count, the Airbnb
  service fee which will be negative, and a cleaning charge. """
  name = models.TextField()
  # Default currency is useless. It will use XYZ if you don't specify.
  value = MoneyField(
      max_digits=10, decimal_places=2, default_currency='XYZ')
  reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE)

  @receiver(pre_save)
  def pre_save(sender, instance, *args, **kwargs):
    if instance.__class__ is ReservationLineItem:
      rental = instance.reservation.listing.rental
      instance.value = rental.set_currency(instance.value)
      # Money fields aren't smart enough to pick up the currency from the field
      # itself when re-saving existing instances. Sigh.
      instance.value_currency = instance.value.currency


class ReservationToPayin(models.Model):
  """ You can receive multiple payins for the same reservation. You can also
  get paid for multiple reservations on the same payin. I've never seen it
  where you have two reservations, each related to two payins, but I wouldn't
  be surprised.
  """
  reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE)
  payin = models.ForeignKey(Payin, on_delete=models.CASCADE)
