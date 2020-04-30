""" A Reservation is made by a Guest against a rental on a channel. It
represents a short term stay at a Rental. This is all non-money reservation
stuff. Money stuff is in reservations/models/money.py and that's where you'll
find Reservation which inherits form ReservationBase. """
from datetime import timedelta
from pytz import timezone
import re
from urllib.parse import quote_plus, urlencode

from django.conf import settings
from django.db import models
from django.shortcuts import reverse

from errors.models import log_error
from guests.models import Guest
from rentals.models import Rental
from util.channels import CHANNEL_OPTIONS, cc_photo_required, AIRBNB
from util.timezone import now, tz_dt_to_tz_dt, midnight_from_date
from util.urls import keys_url


# We also receive statuses inquiry and closed, but we haven't found a use for
# them yet so we just chuck 'em.
CONFIRMED = 'confirmed'
CANCELED = 'canceled'
INQUIRY = 'inquiry'
STATUS_CHOICES = (
    (CONFIRMED, CONFIRMED),
    (CANCELED, CANCELED),
    (INQUIRY, INQUIRY))


class ReservationManagerBase(models.Manager):
  def reservations_in_range(self, from_date, to_date):
    """ Due to timezones, pull back potentially too many reservations and let
    total_and_within do the work of figuring out if that reservation is
    ACTUALLY in the right time. Canceled reservations can have cancellation
    fees and this function gets used for financial reporting, so DON'T filter
    on status. """
    search_check_in = midnight_from_date(to_date) + timedelta(days=1)
    search_check_out = midnight_from_date(from_date) - timedelta(days=1)
    return self.filter(
        is_test_reservation=False,
        check_in__lte=search_check_in,
        check_out__gte=search_check_out,
        rental__is_active=True, rental__is_test_rental=False).select_related(
            'rental', 'guest').order_by('check_in')


class ReservationBase(models.Model):
  channel_id = models.CharField(
      unique=True, db_index=True, max_length=50, help_text=(
          'The id given to this reservation by Airbnb, booking.com, '
          'or whomever.'))
  guest = models.ForeignKey(Guest, on_delete=models.PROTECT)
  anonymized_email = models.CharField(max_length=200, default='', help_text=(
      'jiaxin-ku0lh5ltfwqd0be5@guest.airbnb.com for instance.'))
  check_in = models.DateTimeField(db_index=True)
  check_out = models.DateTimeField(db_index=True)
  check_out_set_at = models.DateTimeField(help_text=(
      '99% of the time, the check_out is set to a time in the future. But '
      'every now and then, the check_out gets set to earlier in the day, '
      'in which case cleanings need to be scheduled based on '
      'check_out_set_at, not check_out, because you cant now begin a '
      'cleaning 5 hours ago.'))
  booked_at = models.DateTimeField()
  canceled_at = models.DateTimeField(null=True, blank=True, db_index=True)
  # Null just because it's new.
  created_at = models.DateTimeField(auto_now_add=True, null=True)
  planned_arrival = models.TimeField(null=True, blank=True, help_text=(
      'This probably shouldnt be used anywhere. Our door code software reads '
      'this value directly from Guesty to enable codes at different times.'))
  planned_departure = models.TimeField(null=True, blank=True, help_text=(
      'The guest explicitly said they intend to depart at this time.'))
  id_verified = models.BooleanField(default=False, help_text=(
      'I understand all channels require ID verification now.'))
  reservation_created = models.DateTimeField(
      default=now, help_text=(
          'Not when was this entry in the db created, this is when the '
          'actual reservation was created. There\'s a delay.'))
  guest_count = models.PositiveIntegerField(null=True, help_text=(
      'How many guests total?'))

  status = models.CharField(
      max_length=100, choices=STATUS_CHOICES, help_text=(
          'This is copied directly from the guesty api. '
          '\'confirmed\' is the good one.'))
  rental = models.ForeignKey(Rental, on_delete=models.PROTECT)
  channel = models.CharField(
      max_length=100, choices=CHANNEL_OPTIONS, help_text=(
          'What channel was this reservation booked on? Don\'t get cute '
          'with this field. Stick to the choices because logic tends to '
          'build up around this.'))

  issues = models.TextField(null=True, blank=True, help_text=(
      'This comes from Notes -> Other in a guesty reservation and is used to '
      'generate the link for the guest feedback form which goes into the '
      'guest_feedback_form_link custom field.'))
  last_synced_at = models.DateTimeField(null=True, blank=True)
  is_test_reservation = models.BooleanField(default=False, help_text=(
      'Dont include test reservations in reports and things.'))
  imported_at = models.DateTimeField(null=True, blank=True, help_text=(
      'If a reservation was imported long after the reservation then payment '
      'information may not be available.'))

  def save(self, nnow=None):
    nnow = nnow or now()
    if self.status == CANCELED and not self.canceled_at:
      raise Exception(
          'If you set the status to canceled, you should specify canceled_at')
    if not self.check_out_set_at:
      self.check_out_set_at = nnow
    super().save()

  def is_airbnb(self):
    return self.channel == AIRBNB

  def set_check_out(self, new_check_out, nnow=None):
    nnow = nnow or now()
    if self.check_out == new_check_out:
      return
    self.check_out = new_check_out
    self.check_out_set_at = nnow
    if self.pk:
      self.save()

  def booked_days_in_advance(self):
    return (self.check_in.date() - self.booked_at.date()).days

  def get_email(self):
    return self.guest.email or self.anonymized_email

  def background_check_required(self):
    return self.rental.building.background_check_guests

  def background_check_valid(self):
    """ This is purposefully vague to hopefully protect the identity of folks
    who fail a background check. Invalid states include opted out, not complete
    in time, and failed. """
    if not self.background_check_required():
      return True
    if self.backgroundcheck_or_none:
      # Purposefully returning only True or False as opposed to True, False,
      # or None. I'm trying really hard to never reveal why a background
      # check is invalid because I don't want anybody finding out who has a
      # criminal record.
      return self.backgroundcheck.passed is True
    if settings.TEST:
      raise Exception('Why doesnt this res have a background check?')
    log_error(
        'Suspicious this reservation doesnt have a background check',
        self.keys_url())
    return False

  def last_minute(self):
    return self.check_in - self.booked_at <= timedelta(hours=48)

  def guest_enters_apartment(self):
    """ Did a guest actually enter the rental? """
    return self.confirmed() or (
        self.canceled() and self.canceled_at and (
            self.check_in < self.canceled_at))

  def get_night_count(self):
    return (self.check_out.date() - self.check_in.date()).days

  def admin_url(self):
    if hasattr(self, 'guestyreservation'):
      return self.guestyreservation.admin_url()
    # We're probably just in tests.
    return 'This reservation isnt from guesty so it doesnt have a url'

  def directions_from_guest_to_rental_url(self):
    return 'https://www.google.com/maps/dir/{}/{}/'.format(
        quote_plus(self.rental.full_address),
        quote_plus(self.guest.airbnb_says_theyre_from))

  def res_deets_url_no_server(self):
    return reverse('va_reservation', kwargs={'pk': self.pk})

  def reservation_history_url(self):
    return '{}{}'.format(
        settings.THIS_SERVERS_BASE_URL,
        self.res_deets_url_no_server())

  def keys_url(self):
    return keys_url(self.res_deets_url_no_server())

  def __repr__(self):
    return '<Reservation {} {} {}>'.format(
        self.pk, self.channel, self.check_in.date())

  def __str__(self):
    return self.__repr__()

  def sync(self, sync=None):
    if not sync:
      from guesty.guesty import Guesty
      sync = Guesty()
    r_long = sync.api.get_one('Reservation', self.guestyreservation.guesty_id)
    sync.sync_reservation(r_long)

  def get_syncer(self):
    try:
      self.guestyreservation
      from guesty.syncer import Syncer
      return Syncer()
    except self.__class__.guestyreservation.RelatedObjectDoesNotExist:
      pass

  def get_guest_feedback_form_link(self):
    from front.models import Front
    params = {
        'guestname': self.guest.full_name,
        'phone': self.guest.phone,
        'address': self.rental.nickname,
        'startdate': self.check_in.date().strftime('%Y-%m-%d'),
        'issues': self.issues,
        'guestlink': self.admin_url(),
        'city': self.rental.building.city.name,
        'reslength': self.get_night_count()}
    convo_id = Front().get_conversation_id(self.guest.phone)
    if convo_id:
      params['frontlink'] = 'https://app.frontapp.com/open/{}'.format(convo_id)
    return 'https://stayd.typeform.com/to/AHNpQk?{}'.format(urlencode(params))

  def latest_submission(self):
    return self.submission_set.order_by('-created_at').first()

  def check_out_date_string(self):
    return self._date_string(self.get_check_out())

  def check_out_time_string(self):
    return self._time_string(self.get_check_out().time())

  def check_in_date_string(self):
    return self._date_string(self.get_check_in())

  def check_in_time_string(self):
    return self._time_string(self.get_check_in().time())

  def _date_string(self, dt):
    return dt.strftime('%A, %B %d').replace(' 0', ' ')

  def _time_string(self, tme):
    trailing_zero = tme.strftime('%I:%M%p').lower()
    leading_zero = trailing_zero.replace(':00', '')
    return re.compile(r'^0').sub('', leading_zero)

  def verify_id_url_no_server(self):
    """ See get_reservation_from_query in
    id_verify.models.SubmissionManager """
    return '{}?{}'.format(
        reverse('verify_id'),
        urlencode({'id': self.channel_id}))

  def verify_id_url(self):
    return '{}{}'.format(
        settings.VERIFY_ID_SERVER, self.verify_id_url_no_server())

  def confirmed(self):
    return self.status == CONFIRMED

  def canceled(self):
    return self.status == CANCELED

  def get_check_in(self):
    return self.tz_dt_to_tz_dt(self.check_in)

  def get_check_out(self):
    return self.tz_dt_to_tz_dt(self.check_out)

  def get_booked_at(self):
    return self.tz_dt_to_tz_dt(self.booked_at)

  def get_reservation_end(self):
    """ This is, like, the soonest maintenance window after the guest left the
    apartment. 99% of the time, this is just the check_out. But if you cancel
    after check in, then some of the reservation still happened, so there is a
    reservation, but it didn't end at the check_out, it ended when it was
    canceled. If you change the checkout to a time in the past, then the
    reservation really went past the checkout, didn't it. This is important for
    things like cleanings. """
    if self.canceled_at and self.canceled_at < self.check_in:
      raise Exception(
          'There is no reservation end because it was canceled before check '
          'in.')

    retroactive_check_out = self.check_out_set_at and (
        self.check_out_set_at > self.check_out)
    if not retroactive_check_out:
      if self.confirmed():
        return self.check_out
      if self.canceled_at and self.canceled_at > self.check_out:
        return self.check_out

    based_on_something_else = None
    if retroactive_check_out:
      based_on_something_else = self.check_out_set_at
    elif self.canceled_at:
      based_on_something_else = self.canceled_at
    else:
      raise Exception(self.keys_url())

    at_time = self.check_out.time()
    something_else_right_time = based_on_something_else.replace(
        hour=at_time.hour, minute=at_time.minute, second=0, microsecond=0)
    if something_else_right_time < based_on_something_else:
      something_else_right_time += timedelta(days=1)
    return something_else_right_time

  def tz_dt_to_tz_dt(self, dt):
    return tz_dt_to_tz_dt(dt, self.rental.building.time_zone)

  def get_overlapping(self):
    if self.confirmed():
      return self.__class__.objects.filter(
          check_in__lt=self.check_out,
          check_out__gt=self.check_in,
          status=CONFIRMED,
          rental=self.rental).exclude(pk=self.pk)
    return self.__class__.objects.none()

  def cc_photo_required(self):
    return cc_photo_required(self.channel)

  def total_and_within(self, from_date, to_date):
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

  def get_is_test_reservation(self):
    return self.is_test_reservation or self.rental.is_test_rental

  class Meta:
    abstract = True
