"""
A Reservation is made by a Guest against a rental on a channel. It represents a
short term stay at a Rental.
"""
from datetime import timedelta
from pytz import timezone
import re

from django.conf import settings
from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.shortcuts import reverse
from django.utils.timezone import now
from django.utils.http import urlencode
from djmoney.models.fields import MoneyField

from guests.models import Guest
from rentals.models import Rental
from util.channels import (
    CHANNEL_OPTIONS, THEY_ASSUME_CC_RISK_CHANNELS, cc_photo_required)
from util.timezone import utc_dt_to_tz_dt, midnight_from_date


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


# We also receive statuses inquiry and closed, but we haven't found a use for
# them yet so we just chuck 'em.
CONFIRMED = 'confirmed'
CANCELED = 'canceled'
STATUS_CHOICES = (
    (CONFIRMED, CONFIRMED),
    (CANCELED, CANCELED))


class ReservationManager(models.Manager):
  def no_cc_info(self):
    """ These are reservations where a successful payment was taken,
    but it was taken in such a way that we don't know the last 4 digits
    of the cc or the type of cc used. In these cases, we can't verify the
    id. These are hopefully rare special cases that must be handled one
    by one. For example, you might load the guesty reservation and just
    go ahead and flip the id verified switch. """
    we_assume_cc_risk = ~models.Q(
        channel__in=THEY_ASSUME_CC_RISK_CHANNELS)
    return self.filter(
        we_assume_cc_risk, valid_payments_exist=True, status=CONFIRMED,
        check_out__gt=now(), cc_last_4__isnull=True,
        guestyreservation__isnull=False, id_verified=False).order_by(
        'check_in')

  def payment_problems(self):
    """ These are reservations where we have to take the payment, but no
    payment has been taken successfully yet. Reservations end up in this
    list if a guest types in their CC info wrong, for instance. """
    we_assume_cc_risk = ~models.Q(
        channel__in=THEY_ASSUME_CC_RISK_CHANNELS)
    return self.filter(
        we_assume_cc_risk, valid_payments_exist=False, status=CONFIRMED,
        check_out__gt=now(), guestyreservation__isnull=False).order_by(
        'check_in')

  def expecting_payments(self):
    return self.filter(
        status=CONFIRMED, check_out__gt=now(), guestyreservation__isnull=False,
        is_paid_in=False)

  def reservations_in_range(self, from_date, to_date, owner_id=None):
    """ Due to timezones, pull back potentially too many reservations and let
    total_days_and_within_from_to do the work of figuring out if that
    reservation is ACTUALLY in the right time.
    This is one of the only actually smart parts in this whole thing.
    Draw timelines to see how it works. """
    search_check_in = midnight_from_date(to_date) + timedelta(days=1)
    search_check_out = midnight_from_date(from_date) - timedelta(days=1)
    reservations = Reservation.objects.filter(
        status=CONFIRMED,
        check_in__lte=search_check_in,
        check_out__gte=search_check_out,
        rental__is_active=True).select_related(
            'rental', 'guest').order_by('check_in')
    if owner_id:
      reservations = reservations.filter(rental__building__owner__pk=owner_id)
    return reservations


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
  planned_arrival = models.TimeField(null=True, blank=True, help_text=(
      'The guest explicitly said they intend to arrive at this time.'))
  planned_departure = models.TimeField(null=True, blank=True, help_text=(
      'The guest explicitly said they intend to depart at this time.'))
  id_verified = models.BooleanField(default=False, help_text=(
      'I understand all channels require ID verification now.'))
  reservation_created = models.DateTimeField(
      default=now, help_text=(
          'Not when was this entry in the db created, this is when the '
          'actual reservation was created. There\'s a delay.'))
  # Default currency is useless. It will use XYZ if you don't specify.
  price_per_night = MoneyField(
      max_digits=10, decimal_places=2, default_currency='XYZ', help_text=(
          'Uh, this is a bit of a mess. Don\'t do anything important with '
          'it.'))
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
  balance_due = MoneyField(
      max_digits=10, decimal_places=2, default_currency='XYZ', null=True,
      blank=True, help_text=(
          'Basically we care if this is positive, zero, or negative.'))
  valid_payments_exist = models.BooleanField(default=False, help_text=(
      'Were there ANY valid payments made against this reservation? '
      'This only really matters on channels where we assume the payment '
      'risk.'))
  security_deposit = MoneyField(
      max_digits=10, decimal_places=2, default_currency='XYZ', null=True,
      blank=True, help_text=(
          'The amount of the hold placed on a credit card for this '
          'reservation.'))
  status = models.CharField(
      max_length=100, choices=STATUS_CHOICES, help_text=(
          'This is copied directly from the guesty api. '
          '\'confirmed\' is the good one.'))
  rental = models.ForeignKey(Rental, on_delete=models.CASCADE, null=True)
  channel = models.CharField(
      max_length=100, choices=CHANNEL_OPTIONS, help_text=(
          'What channel was this reservation booked on? Don\'t get cute '
          'with this field. Stick to the choices because logic tends to '
          'build up around this.'))
  cc_last_4 = models.CharField(max_length=4, null=True, blank=True, help_text=(
      'We only get the last 4 digits of the cc on channels where we assume '
      'the payment risk, such as Booking.com, AND where a successful payment '
      'occured. This field gets compared to a picture of the guests credit '
      'card by an admin as part of the id verifcation flow.'))
  cc_brand = models.CharField(max_length=20, null=True, blank=True, help_text=(
      'Same story as cc_last_4.'))

  objects = ReservationManager()

  def admin_url(self):
    return self.guestyreservation.admin_url()

  def sync(self):
    from guesty.guesty import Guesty
    sync = Guesty()
    sync.sync_reservation(sync.api.get_one(
        Reservation, self.guestyreservation.guesty_id))

  def get_syncer(self):
    from guesty.syncer import Syncer
    return Syncer()

  def latest_submission(self):
    return self.submission_set.order_by('-created_at').first()

  def has_security_deposit(self):
    return bool(self.security_deposit)

  def has_payment_problem(self):
    return Reservation.objects.payment_problems().filter(pk=self.pk).exists()

  def check_out_date_string(self):
    return self._date_string(self.get_check_out())

  def check_out_time_string(self):
    return self._time_string(
        self.planned_departure or self.get_check_out().time())

  def check_in_date_string(self):
    return self._date_string(self.get_check_in())

  def check_in_time_string(self):
    return self._time_string(
        self.planned_departure or self.get_check_in().time())

  def _date_string(self, dt):
    return dt.strftime('%A, %B %d').replace(' 0', ' ')

  def _time_string(self, tme):
    trailing_zero = tme.strftime('%I:%M%p').lower()
    leading_zero = trailing_zero.replace(':00', '')
    return re.compile(r'^0').sub('', leading_zero)

  def verify_id_url_no_server(self):
    """ See get_reservation_from_verify_id_query in
    id_verify.models.SubmissionManager """
    return '{}?{}'.format(
        reverse('verify_id'),
        urlencode({'id': self.channel_reservation_id}))

  def verify_id_url(self):
    return '{}{}'.format(
        settings.VERIFY_ID_SERVER, self.verify_id_url_no_server())

  def confirmed(self):
    return self.status == 'confirmed'

  def get_check_in(self):
    return utc_dt_to_tz_dt(self.check_in, self.rental.building.time_zone)

  def get_check_out(self):
    return utc_dt_to_tz_dt(self.check_out, self.rental.building.time_zone)

  def get_booked_at(self):
    return utc_dt_to_tz_dt(self.booked_at, self.rental.building.time_zone)

  def get_overlapping(self):
    if self.confirmed():
      return Reservation.objects.filter(
          check_in__lt=self.check_out,
          check_out__gt=self.check_in,
          status=CONFIRMED,
          rental=self.rental).exclude(pk=self.pk)

  def line_items(self):
    """ This just gets used in tests I think. """
    return ReservationLineItem.objects.filter(reservation=self)

  def we_assume_cc_risk(self):
    return self.channel not in THEY_ASSUME_CC_RISK_CHANNELS

  def cc_photo_required(self):
    return cc_photo_required(self.channel)

  def total_days_and_within_from_to(self, from_date, to_date):
    """ Returns (total days in this reservation, # of those days that fall in
    the range from_date, to_date) This is a little tricky. People check out on
    one day and then somebody new checks in on the same day. So a reservation
    counts as being on a day if you're staying through that night. If you
    checkin on the 15th and out on the 16th, 100% of the revenue counts towards
    the 15th. to_date is exclusive, so querying from the 15th to the 15th will
    always return 0. So if you want to know about January, query from January
    1st to February 1st, which if you think about it, is the checkout day and
    doesn't count towards revenue.

    This computes based on the timezone of the rental, so if you query for
    Tuesday you'll get this reservation's rental's understanding of Tuesday,
    not some global understaind of Tuesday. """
    tzinfo = timezone(self.rental.building.time_zone)
    from_dt = midnight_from_date(from_date, tzinfo)
    to_dt = midnight_from_date(to_date, tzinfo)
    within = 0
    total_days = 0
    on = self.get_check_in()
    check_out = self.get_check_out()
    while on < check_out:
      total_days += 1
      if from_dt <= on and on <= to_dt:
        within += 1
      on += timedelta(days=1)
    return (total_days, within)

  @receiver(pre_save)
  def pre_save(sender, instance, *args, **kwargs):
    """ This is ugly. For starters, it doesn't run during, say,
    Reservation.objects.filter(whatever).update(whatever). But timezones
    and currencies are REALLY ugly, using all kinds of defaults and
    assumptions, or not using as the case may be. The moral of the story
    is, we gotta be careful with those. """
    if instance.__class__ is Reservation:
      rental = instance.rental
      instance.check_in = rental.building.set_timezone(instance.check_in)
      instance.check_out = rental.building.set_timezone(instance.check_out)
      instance.price_per_night = rental.building.set_currency(
          instance.price_per_night)
      instance.total_payin = rental.building.set_currency(instance.total_payin)


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
