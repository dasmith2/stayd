"""
A Reservation is made by a Guest against a Listing. It represents a short
term stay at a Rental.
"""

from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver
from djmoney.models.fields import MoneyField
from django.utils import timezone

from guests.models import Guest
from listings.models import Listing
from util.channels import CHANNELS
from util.timezone import utc_dt_to_tz_dt


class KNOWN_LINE_ITEM_NAMES:
  """ I found these with this query on the production database:
  SELECT DISTINCT(name) FROM reservations_reservationlineitem;
  Host channel fee and Airbnb Service Fee are negative.
  As you can see, capitalization is hit and miss. This is because many of these
  are typed in manually!
  """
  def is_channel_fee(self, name):
    return name.lower() in [ty.lower() for ty in self.CHANNEL_FEE_NAMES]

  def is_cleaning(self, name):
    return name.lower() in [ty.lower() for ty in self.CLEANING_NAMES]

  def is_rent(self, name):
    return name.lower() in [ty.lower() for ty in self.RENT_NAMES]

  def is_rent_or_correction(self, name):
    types = self.RENT_NAMES + self.CORRECTION_NAMES
    return name.lower() in [ty.lower() for ty in types]

  def is_tax(self, name):
    return name.lower() in [ty.lower() for ty in [self.CITY_TAX]]

  CITY_TAX = 'CITY_TAX'

  HOST_CHANNEL_FEE = 'Host channel fee'
  AIRBNB_SERVICE_FEE = 'Airbnb Service Fee'
  CHANNEL_FEE_NAMES = [HOST_CHANNEL_FEE, AIRBNB_SERVICE_FEE]

  RENT = 'Rent'
  ACCOMMODATION_FARE = 'Accommodation fare'
  RENT_NAMES = [RENT, ACCOMMODATION_FARE]

  # These happen because Guesty isn't smart enough to handle (I think they're
  # called) "service fees" of 14.5% that we add on Booking.com to compensate
  # for the fees they charge us. So for existing reservations that used that
  # mechanism we had to add corrections to Guesty to make the numbers add up
  # so Guesty will charge the guest exactly what we quoted them.
  CORRECTION = 'correction'
  GUESTY_CORRECTION = 'Guesty correction'
  REFUND = 'Refund'
  CORRECTION_NAMES = [CORRECTION, GUESTY_CORRECTION, REFUND]

  CLEANING_FEES = 'Cleaning Fees'
  CLEANING_FEE = 'Cleaning fee'
  CLEANING_NAMES = [CLEANING_FEES, CLEANING_FEE]


CONFIRMED = 'confirmed'
CANCELED = 'canceled'
STATUS_CHOICES = (
    (CONFIRMED, CONFIRMED),
    (CANCELED, CANCELED))


class Reservation(models.Model):
  channel_reservation_id = models.CharField(
      unique=True, db_index=True, max_length=50, help_text=(
          'The id given to this reservation by Airbnb, booking.com, '
          'or whomever.'))
  guest = models.ForeignKey(Guest, on_delete=models.CASCADE)
  anonymized_email = models.CharField(max_length=200, default='', help_text=(
      'jiaxin-ku0lh5ltfwqd0be5@guest.airbnb.com for instance.'))
  check_in = models.DateTimeField(db_index=True)
  check_out = models.DateTimeField(db_index=True)
  booked_at = models.DateTimeField(null=True, blank=True)
  # If this is set, don't send them an SMS asking for a check_in time.
  # We want check_in times because... No idea actually.
  planned_arrival = models.TimeField(null=True, blank=True, help_text=(
      'The guest explicitly said they intend to arrive at this time.'))
  planned_departure = models.TimeField(null=True, blank=True, help_text=(
      'The guest explicitly said they intend to depart at this time.'))
  id_verified = models.BooleanField(default=False, help_text=(
      'I understand all channels require ID verification now.'))
  reservation_created = models.DateTimeField(
      default=timezone.now, help_text=(
          'Not when was this entry in the db created, this is when the '
          'actual reservation was created. There\'s a delay.'))
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
  security_deposit = MoneyField(
      max_digits=10, decimal_places=2, default_currency='XYZ', null=True,
      blank=True, help_text=(
          'The amount of the hold placed on a credit card for this '
          'reservation.'))
  status = models.CharField(
      max_length=100, choices=STATUS_CHOICES, help_text=(
          'This is copied directly from the guesty api. '
          '\'confirmed\' is the good one.'))
  listing = models.ForeignKey(Listing, on_delete=models.CASCADE, null=False)
  display_channel = models.CharField(
      max_length=100, choices=CHANNELS, null=True, blank=True, help_text=(
          'If we set a booking up manually, then there won\'t be all '
          'the Airbnb fields and stuff available, but the SMSs should still '
          'reflect whatever source was chosen manually in Guesty.'))
  cleaning_notes = models.TextField(default='', help_text=(
      'Reme fills this in because at the moment she\'s in charge of all our '
      'cleaning.'))

  def has_security_deposit(self):
    return bool(self.security_deposit)

  def check_out_time_string(self):
    time = self.planned_departure or self.get_check_out().time()
    return time.strftime('%I:%M %p').lower().replace(':00', '')

  def confirmed(self):
    return self.status == 'confirmed'

  def get_check_in(self):
    return utc_dt_to_tz_dt(self.check_in, self.listing.rental.time_zone)

  def get_check_out(self):
    return utc_dt_to_tz_dt(self.check_out, self.listing.rental.time_zone)

  def get_booked_at(self):
    return utc_dt_to_tz_dt(self.booked_at, self.listing.rental.time_zone)

  def get_overlapping(self):
    return Reservation.objects.filter(
        check_in__lt=self.check_out,
        check_out__gt=self.check_in,
        status=CONFIRMED,
        listing__rental=self.listing.rental).exclude(pk=self.pk)

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
  name = models.TextField(help_text=(
      'I don\'t know for sure what these can be, but see '
      'KNOWN_LINE_ITEM_NAMES for what I\'ve seen so far.'))
  # Default currency is useless. It will use XYZ if you don't specify.
  value = MoneyField(
      max_digits=10, decimal_places=2, default_currency='XYZ')
  reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE)

  def __repr__(self):
    return 'ReservationLineItem({}) {} {}'.format(
        self.pk, self.name, self.value)
