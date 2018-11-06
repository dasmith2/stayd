from collections import namedtuple
from datetime import timedelta
import json

from django.db import models
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.dateparse import parse_datetime
from django.utils.timezone import now
from djmoney.models.fields import MoneyField

from errors.models import log_error
from properly.api import API
from properly.models.message_sender import MessageSender
from rentals.models import Building, Rental
from reservations.models import Reservation
from util.background import background
from util.html_status_codes import get_json
from util.rm_old import RmOldManager
from util.signals import post_sync
from util.timezone import tz_dt_to_tz_dt, get_readable_duration


JOBS_START_AFTER_CHECKOUT = timedelta(minutes=15)


def properly_datetime_format(dt):
  return tz_dt_to_tz_dt(dt, 'UTC').isoformat().replace('+00:00', 'Z')


class Checklist(models.Model):
  name = models.CharField(max_length=200)
  properly_id = models.CharField(max_length=200, help_text=(
      'If the URL for the checklist is '
      'https://app.getproperly.com/#/checklists/Lcx3tM5HAB/1K6BGKUQlK/ '
      'then the properly_id is 1K6BGKUQlK'))

  def __str__(self):
    return self.name


class RentalChecklist(models.Model):
  rental = models.ForeignKey(Rental, on_delete=models.CASCADE)
  properly_rental_id = models.CharField(
      max_length=200, null=True, blank=True, help_text=(
          'If the URL for the property is '
          'https://app.getproperly.com/#/properties/Dzb3DEE0zD/checklists '
          'then the properly_rental_id is Dzb3DEE0zD'))
  checklist = models.ForeignKey(
      Checklist, on_delete=models.CASCADE, null=True, blank=True)
  cleaning_duration = models.PositiveIntegerField(default=3)
  source_property_id = models.CharField(
      max_length=100, null=True, blank=True, help_text=(
          'Dont set this manually. The source_property_id must be set via the '
          'property.update command so it can populate the sourcePropertyId '
          'field of the jobRequest.create command.'))

  def get_source_property_id(self, api=API()):
    if not self.properly_rental_id:
      raise Exception(
          'You have to set the properly_rental_id before you can set the '
          'source_property_id')
    desired_source_property_id = self.properly_rental_id
    if desired_source_property_id != self.source_property_id:
      if api.response_is_ok(api.property_update({
          'propertyId': self.properly_rental_id,
          'changes': {
              'sourceId': desired_source_property_id}})):
        self.source_property_id = desired_source_property_id
        self.save()
    return self.source_property_id


@receiver(post_save, sender=RentalChecklist)
def post_rental_checklist_save(sender, instance, *args, **kwargs):
  if instance.properly_rental_id and not instance.source_property_id:
    set_rental_checklist_source_property_id(instance)


@background
def set_rental_checklist_source_property_id(rental_checklist):
  rental_checklist.get_source_property_id()


@receiver(post_sync, sender=Rental)
def post_rental_sync(sender, instance, *args, **kwargs):
  RentalChecklist.objects.get_or_create(rental=instance)


@receiver(post_sync, sender=Reservation)
def post_reservation_sync(sender, instance, *args, **kwargs):
  # We aren't ready for this just yet.
  # Cleaning.objects.handle_res_sync(instance, kwargs.get('api', API()))
  # Booking.objects.handle_res_sync(instance, kwargs.get('api', API()))
  pass


class BookingManager(models.Manager):
  def get_create_booking_data(self, booking):
    res = booking.reservation
    rental_checklist = self._get_rental_checklist(res)
    if not rental_checklist:
      raise Exception(
          'The RentalChecklist for rental {} doesnt exist yet'.format(
              res.rental.pk))

    title = 'API reservation for {}'.format(
        res.guest.get_name())
    return {
        'sourcePropertyId': rental_checklist.source_property_id,
        'sourceBookingId': booking.get_source_booking_id(),
        'startDate': properly_datetime_format(res.check_in),
        'endDate': properly_datetime_format(res.check_out),
        'title': title,
        'numberOfGuests': 1,
        'guestDetails': [{
            'sourceId': str(res.guest.channel_id),
            'firstName': res.guest.first_name or '',
            'lastName': res.guest.last_name or ''}]}

  def create_booking(self, reservation, api):
    booking = Booking(reservation=reservation)
    got = api.booking_create(self.get_create_booking_data(booking))
    if api.response_is_ok(got):
      booking.booking_id = get_json(got)['booking.create'][0]['bookingId']
      booking.save()

  def handle_res_sync(self, reservation, api):
    booking = self.filter(reservation=reservation).first()
    if not booking:
      if reservation.confirmed():
        checklist = self._get_rental_checklist(reservation)
        if checklist and checklist.source_property_id:
          # This is often the case in tests. I don't want the stats tests, say,
          # to know about rental checklists or whatever.
          self.create_booking(reservation, api)

  def _get_rental_checklist(self, reservation):
    return RentalChecklist.objects.filter(
        rental=reservation.rental).first()


class Booking(models.Model):
  booking_id = models.CharField(max_length=200, help_text=(
      'This comes from Properly in the response to the booking.create call.'))
  reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE)

  objects = BookingManager()

  def get_source_booking_id(self):
    return self.reservation.channel_reservation_id


class Cleaner(models.Model):
  name = models.CharField(max_length=200)
  # Do I need phone and email? Waiting to hear back from Properly.
  phone = models.CharField(max_length=50)
  email = models.CharField(max_length=100)
  hourly_rate = MoneyField(
      max_digits=10, decimal_places=2, default_currency='USD')
  buildings = models.ManyToManyField(Building)

  def __str__(self):
    return self.name

  def __repr__(self):
    return '<Cleaner(name={}, phone={}, email={})>'.format(
        self.name, self.phone, self.email)


class CleaningManager(models.Manager):
  def create_job_request(self, reservation, api):
    if self.filter(reservation=reservation).first():
      raise Exception('This job request was created already.')
    cleaning = Cleaning.objects.create(
        reservation=reservation,
        offered_start_time=Cleaning.objects.get_start_time(reservation))
    cleaning.offered_to.set(self.available_cleaners(reservation))
    cleaning.create_job_request(api)
    return cleaning

  def get_start_time(self, reservation):
    return reservation.check_out + JOBS_START_AFTER_CHECKOUT

  def available_cleaners(self, reservation):
    all_building_cleaners = set(Cleaner.objects.filter(
        buildings=reservation.rental.building))
    existing_cleanings = Cleaning.objects.filter(
        reservation__check_out__date=reservation.check_out.date(),
        accepted_by__in=all_building_cleaners)
    busy_cleaners = set(
        [clean.accepted_by for clean in existing_cleanings])
    return list(all_building_cleaners - busy_cleaners)

  def require_cleanings(self, nnow=None):
    nnow = nnow or now()
    return Reservation.objects.raw(
        'SELECT res.* FROM '
        'reservations_reservation AS res '
        'LEFT OUTER JOIN properly_cleaning AS clean '
        'ON res.id = clean.reservation_id '
        'WHERE clean.reservation_id IS NULL '
        'AND res.check_out >= %s '
        'AND res.check_out < %s '
        'AND res.balance_due <= 0.01 '
        'AND res.id_verified = true '
        'ORDER BY res.check_out;',
        [nnow, nnow + timedelta(days=7)])

  def todays_cleanings(self, nnow=None):
    nnow = nnow or now()
    return self.filter(
        reservation__check_out__date=nnow.date(), accepted_by__isnull=False)

  def create_job_requests(self, nnow=None, api=API()):
    nnow = nnow or now()
    return [self.create_job_request(
        res, api) for res in self.require_cleanings(nnow)]

  def uh_oh_unclaimed(self, nnow=None):
    """ Return all cleanings that are more than 3 hours old, start within 48
    hours, and are unclaimed. """
    nnow = nnow or now()
    # start = check out + 15, and we want start is in the next 48 hours, so
    # check out + 15 <= 48 hours from now, so check_out <= 48 hours from now -
    # 15.
    check_out_lt = nnow + timedelta(hours=48) - JOBS_START_AFTER_CHECKOUT
    # Just so we aren't notifying of cleanings that were supposed to happen
    # last week or something.
    check_out_gt = nnow - timedelta(hours=1)
    return self.filter(
        created_at__lte=nnow - timedelta(hours=3),
        reservation__check_out__gte=check_out_gt,
        reservation__check_out__lte=check_out_lt,
        accepted_by__isnull=True)

  def taking_too_long(self, nnow):
    nnow = nnow or now()
    to_return = []
    for cleaning in self.todays_cleanings(nnow):
      to_time = cleaning.completed_at or nnow
      duration = to_time - cleaning.started_at
      if duration.seconds > 3 * 60 * 60 + 30 * 60:  # 3.5 hours
        to_return.append(cleaning)
    return to_return

  def hours_and_pay(self, from_date, to_date):
    lookup = {}
    to_return = []
    for cleaning in Cleaning.objects.filter(
        completed_at__date__gte=from_date, completed_at__date__lt=to_date):
      if cleaning.accepted_by not in lookup:
        lookup[cleaning.accepted_by] = []
      lookup[cleaning.accepted_by].append(cleaning)
    for cleaner, cleanings in sorted(
        lookup.items(), key=lambda x: x[0].name):
      duration = sum(
          [cleaning.get_duration() for cleaning in cleanings], timedelta())
      hours = duration.seconds / 3600.0
      hourly_rate = float(cleaner.hourly_rate.amount)
      to_return.append(HoursAndPayRow(
          cleaner_name=cleaner.name, cleanings=len(cleanings),
          hours=hours,
          hourly_rate=hourly_rate,
          total_earnings=hours * hourly_rate))
    return to_return

  def handle_res_sync(self, reservation, api):
    cleaning = self.filter(reservation=reservation).first()
    if cleaning:
      if not reservation.confirmed():
        cleaning.cancel(api)
      elif cleaning.get_start_time() != cleaning.offered_start_time:
        cleaning.cancel(api)
        Cleaning.objects.create_job_request(reservation, api)


class HoursAndPayRow(
    namedtuple(
        'HoursAndPayRow',
        'cleaner_name cleanings hours hourly_rate total_earnings')):
  pass


class Cleaning(models.Model):
  offered_to = models.ManyToManyField(
      Cleaner, related_name='offered_to', help_text=(
          'Who can see this job offer in their Properly app?'))
  accepted_by = models.ForeignKey(
      Cleaner, related_name='accepted_by', on_delete=models.CASCADE,
      null=True, blank=True, help_text='Who actually took the job?')
  reservation = models.ForeignKey(
      Reservation, on_delete=models.CASCADE, help_text=(
          'The reservation this cleaning happens after.'))
  job_request_id = models.CharField(
      max_length=100, null=True, blank=True, help_text=(
          'This comes back in the response to the create_job request. You '
          'need it to create an update request.'))
  created_at = models.DateTimeField(auto_now_add=True)
  creation_confirmed = models.DateTimeField(null=True, blank=True)
  started_at = models.DateTimeField(null=True, blank=True)
  completed_at = models.DateTimeField(null=True, blank=True)
  offered_start_time = models.DateTimeField(help_text=(
      'We have to keep track of what time this cleaning was originally '
      'scheduled for so we can notice if the cleaning time changes due '
      'to a change in the reservation.'))

  objects = CleaningManager()

  def is_complete(self):
    return bool(self.completed_at)

  def overlapping(self):
    if not self.accepted_by:
      return []  # otherwise, below you're asking accepted_by=None
    return Cleaning.objects.filter(
        ~Q(pk=self.pk), accepted_by=self.accepted_by,
        offered_start_time=self.offered_start_time)

  def remove_offered_to(self, cleaner, api):
    self.offered_to.remove(cleaner)
    self.push_updated_offered_to(api)

  def cancel(self, api):
    got = api.job_request_cancel(self.job_request_id)
    if api.response_is_ok(got):
      self.delete()
    else:
      log_error('Error canceling cleaning', (self.pk, got.content))

  def get_duration(self, nnow=None):
    if not self.started_at:
      raise Exception((
          'A cleaning must have a started_at in order to '
          'have a duration').format(self.started_at))
    to = self.completed_at or nnow or now()
    return to - self.started_at

  def get_readable_duration(self, nnow):
    return get_readable_duration(self.get_duration(nnow))

  def get_cost(self):
    return self.accepted_by.hourly_rate * (
        self.completed_at - self.started_at).hours

  def get_address_and_time(self):
    address = self.reservation.rental.full_address
    return '{} {}'.format(
        address, self.get_readable_time_str(
            self._get_tz_dt(self.get_start_time())))

  def get_readable_time_str(self, dt):
    if dt.tzname() == 'UTC':
      dt = self._get_tz_dt(dt)
    return dt.strftime('%I:%M%p').lower()

  def get_full_start_time_str(self):
    return self._get_tz_dt(
        self.get_start_time()).strftime('%Y-%m-%d %I:%M%p').lower()

  def _get_tz_dt(self, dt):
    # Why are timezones such a pain.
    time_zone = self.reservation.rental.building.time_zone
    return tz_dt_to_tz_dt(dt, time_zone)

  def get_start_time(self):
    return Cleaning.objects.get_start_time(self.reservation)

  def create_job_request(self, api):
    created_json = get_json(api.job_request_create(self._create_job_data()))
    if created_json:
      self.creation_confirmed = now()
      self.job_request_id = created_json[
          'jobRequest.create'][0]['jobRequestId']
      self.save()
    return created_json

  def push_updated_offered_to(self, api):
    api.job_request_update({
        'jobRequestId': self.job_request_id,
        'changes': {
            'serviceProviders': self._get_service_providers()}})

  def _create_job_data(self):
    rental_checklist = RentalChecklist.objects.filter(
        rental=self.reservation.rental).first()
    if not rental_checklist or not rental_checklist.checklist:
      raise Exception('Rental {} needs a checklist.'.format(
          self.reservation.rental))
    if not rental_checklist.properly_rental_id:
      raise Exception('Rental {} needs a properly_rental_id'.format(
          self.reservation.rental))
    checklist = rental_checklist.checklist.properly_id
    source_property_id = rental_checklist.get_source_property_id()
    booking = Booking.objects.get(reservation=self.reservation)
    return {
        'sourceBookingId': booking.get_source_booking_id(),
        'receiveUpdates': True,
        'time': {
            'type': 'fixed',  # Not totally sure about this field
            'startTime': properly_datetime_format(self.get_start_time()),
            'durationInHours': rental_checklist.cleaning_duration},
        'property': {'sourcePropertyId': source_property_id},
        'checklists': [{'checklistId': checklist}],
        'serviceProviders': self._get_service_providers()}

  def _get_service_providers(self):
    service_providers = []
    for cleaner in self.offered_to.all():
      service_providers.append({'email': cleaner.email})
    return service_providers

  class Meta:
    ordering = ('started_at',)


class RawEvent(models.Model):
  json = models.TextField(help_text='The raw json string from the request.')
  created_at = models.DateTimeField(auto_now_add=True, db_index=True)
  handled_at = models.DateTimeField(null=True, blank=True)

  objects = RmOldManager()

  def handle(self, api=API(), message_sender=MessageSender()):
    data = json.loads(self.json)

    event_name = data.get('eventName', None)
    result_0 = data.get('results', [None])[0]
    if result_0:
      cleaning = Cleaning.objects.get(job_request_id=result_0['jobRequestId'])
      created_at = parse_datetime(data['createdAt'])
      stuff_happened = True
      if event_name == 'jobRequest.accepted':
        self.handle_accepted_job_request(cleaning, data, api)
      elif event_name == 'jobRequest.canceledByServiceProvider':
        self.handle_canceled_by_cleaner(cleaning, data, api)
      elif event_name == 'jobRequest.started':
        cleaning.started_at = created_at
        cleaning.save()
      elif event_name == 'jobRequest.completed':
        cleaning.completed_at = created_at
        cleaning.save()
      else:
        stuff_happened = False
      if stuff_happened:
        post_sync.send(
            sender=Cleaning, instance=cleaning, message_sender=message_sender)
    self.handled_at = now()
    self.save()

  def handle_accepted_job_request(self, cleaning, data, api):
    cleaner = Cleaner.objects.get(email=data['results'][0]['serviceProvider'])
    cleaning.accepted_by = cleaner
    cleaning.save()
    for other_offer in Cleaning.objects.filter(
        accepted_by__isnull=True, offered_to=cleaner,
        offered_start_time=cleaning.offered_start_time):
      other_offer.remove_offered_to(cleaner, api)

  def handle_canceled_by_cleaner(self, cleaning, data, api):
    cleaning.cancel(api)
    Cleaning.objects.create_job_request(cleaning.reservation, api)
