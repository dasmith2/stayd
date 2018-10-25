from datetime import timedelta, date

from django.db import models
from django.dispatch import receiver
from django.utils.timezone import now
from djmoney.models.fields import MoneyField

from properly.api import API
from rentals.models import Building, Rental
from reservations.models import Reservation
from util.rm_old import RmOldManager
from util.html_status_codes import get_json
from util.signals import post_sync
from util.timezone import utc_dt_to_tz_dt


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
    if not self.source_property_id:
      if not self.properly_rental_id:
        raise Exception(
            'You have to set the properly_rental_id before you can set the '
            'source_property_id')
      if api.response_is_ok(api.property_update({
          'propertyId': self.properly_rental_id,
          'changes': {
              'sourceId': self.properly_rental_id}})):
        self.source_property_id = self.properly_rental_id
        self.save()
    return self.source_property_id


@receiver(post_sync, sender=Rental)
def post_rental_sync(sender, instance, *args, **kwargs):
  RentalChecklist.objects.get_or_create(rental=instance)


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
  def available_cleaners(self, reservation):
    all_building_cleaners = set(Cleaner.objects.filter(
        buildings=reservation.rental.building))
    existing_cleanings = Cleaning.objects.filter(
        reservation__check_out__date=reservation.check_out.date(),
        accepted_by__in=all_building_cleaners)
    busy_cleaners = set(
        [clean.accepted_by for clean in existing_cleanings])
    return list(all_building_cleaners - busy_cleaners)

  def require_cleanings(self):
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
        [now(), now() + timedelta(days=7)])

  def todays_cleanings(self):
    return self.filter(
        reservation__check_out__date=date.today(), accepted_by__isnull=False)

  def create_job_requests(self, api=API()):
    return [self.create_job_request(
        res, api=api) for res in self.require_cleanings()]

  def create_job_request(self, reservation, api=API()):
    if self.filter(reservation=reservation).first():
      raise Exception('This job request was created already.')
    cleaning = Cleaning.objects.create(reservation=reservation)
    cleaning.offered_to.set(self.available_cleaners(reservation))
    cleaning.create_job_request(api=api)
    return cleaning


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

  objects = CleaningManager()

  def get_cost(self):
    return self.accepted_by.hourly_rate * (
        self.completed_at - self.started_at).hours

  def get_address_and_time(self):
    address = self.reservation.rental.full_address

    # Why are timezones such a pain.
    time_zone = self.reservation.rental.building.time_zone
    start_time = utc_dt_to_tz_dt(self.get_start_time(), time_zone)
    start_time_str = start_time.strftime('%I:%M%p').lower()

    return '{} {}'.format(address, start_time_str)

  def create_job_request(self, api=API()):
    created_json = get_json(api.job_request_create(self._create_job_data()))
    if created_json:
      self.creation_confirmed = now()
      self.job_request_id = created_json[
          'jobRequest.create'][0]['jobRequestId']
      self.save()
    return created_json

  def update_cleaners(self, api=API()):
    api.job_request_update(self._update_cleaners_data())

  def get_start_time(self):
    return self.reservation.check_out + timedelta(minutes=15)

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
    start_time = self.get_start_time().isoformat().replace('+00:00', 'Z')
    return {
        'sourceBookingId': self.reservation.channel_reservation_id,
        'receiveUpdates': True,
        'time': {
            'type': 'fixed',  # Not totally sure about this field
            'startTime': start_time,
            'durationInHours': rental_checklist.cleaning_duration},
        'property': {'sourcePropertyId': source_property_id},
        'checklists': [{'checklistId': checklist}],
        'serviceProviders': self._get_service_providers()}

  def _update_cleaners_data(self):
    return {
        'jobRequestId': self.job_request_id,
        'changes': {
            'receiveUpdates': True,
            'serviceProviders': self._get_service_providers()}}

  def _get_service_providers(self):
    service_providers = []
    for cleaner in self.offered_to.all():
      service_providers.append({'email': cleaner.email})
    return service_providers


class RawEvent(models.Model):
  json = models.TextField(help_text='The raw json string from the request.')
  created_at = models.DateTimeField(auto_now_add=True, db_index=True)
  handled_at = models.DateTimeField(null=True, blank=True)

  objects = RmOldManager()
