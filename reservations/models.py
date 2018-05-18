"""
A Reservation is made by a Guest against a Listing. It represents a short
term stay at a Rental.

Owner payouts are a whole thing, so I figured I'd better put them in an app
by themselves so they don't clutter this up. In order to update the owner
payout of a reservation, do something like this.

from owner_payouts.models import ReservationToPayout
ReservationToPayout.objects.update_payout(my_reservation)
"""

from datetime import timedelta

from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver
from djmoney.models.fields import MoneyField
from django.utils import timezone

from guests.models import Guest
from listings.models import Listing
from pays.models import Payin
from util.channels import AIRBNB
from util.timezone import utc_dt_to_tz_dt


class Reservation(models.Model):
  channel_reservation_id = models.CharField(
      db_index=True, max_length=50, help_text=(
          'The id given to this reservation by Airbnb, booking.com, '
          'or whomever.'))
  guest = models.ForeignKey(Guest, on_delete=models.CASCADE)
  anonymized_email = models.CharField(max_length=200, default='', help_text=(
      'jiaxin-ku0lh5ltfwqd0be5@guest.airbnb.com for instance.'))
  check_in = models.DateTimeField()
  check_out = models.DateTimeField()
  booked_at = models.DateTimeField(null=True, blank=True)
  # If this is set, don't send them an SMS asking for a check_in time.
  # We want check_in times because... No idea actually.
  planned_arrival = models.TimeField(null=True, blank=True, help_text=(
      'The guest explicitly said they intend to arrive at this time.'))
  id_verified = models.BooleanField(default=False, help_text=(
      'I understand all channels require ID verification now.'))
  reservation_created = models.DateTimeField(default=timezone.now)
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
      'transactions, a.k.a. mama got paid.'))
  status = models.CharField(max_length=100, null=True, help_text=(
      'At the moment this is simply copied directly from the guesty api. '
      '\'confirmed\' is the good one, basically.'))
  listing = models.ForeignKey(Listing, on_delete=models.CASCADE, null=False)
  auto_communicate = models.BooleanField(default=False, help_text=(
      'Whether or not to allow automatic SMSs to go through. This manual '
      'field should go away when we\'re confident in the Guesty '
      'integration\'s ability to manage messages.'))

  def get_check_in(self):
    return utc_dt_to_tz_dt(self.check_in, self.listing.rental.time_zone)

  def get_check_out(self):
    return utc_dt_to_tz_dt(self.check_out, self.listing.rental.time_zone)

  def get_booked_at(self):
    return utc_dt_to_tz_dt(self.booked_at, self.listing.rental.time_zone)

  def when_did_we_get_paid(self):
    if not self.is_paid_in:
      return
    channel = self.listing.channel
    if channel == AIRBNB:
      return self.check_in + timedelta(days=1)
    else:
      raise Exception(
          'when_did_we_get_paid isn\'t implemented for {} yet'.format(channel))

  def line_items(self):
    """ This, like channel_listing_id(), is mainly for the benefit of the
    serializer. But it's kind of handy so it gets used in tests too.
    """
    return ReservationLineItem.objects.filter(reservation=self)

  @receiver(pre_save)
  def pre_save(sender, instance, *args, **kwargs):
    """ This is ugly. For starters, it doesn't run during, say,
    Reservation.objects.filter(whatever).update(whatever). But timezones
    and currencies are REALLY ugly, using all kinds of defaults and
    assumptions, or not using as the case may be. The moral of the story
    is, we gotta be careful with those. """
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


class ReservationToPayin(models.Model):
  """ You can receive multiple payins for the same reservation. You can also
  get paid for multiple reservations on the same payin. I've never seen it
  where you have two reservations, each related to two payins, but I wouldn't
  be surprised.

  OK this too came from the scraper. When it's officially settled how we know
  we got paid from the Guesty API then this can go away.
  """
  reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE)
  payin = models.ForeignKey(Payin, on_delete=models.CASCADE)
