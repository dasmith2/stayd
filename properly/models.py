from datetime import timedelta

from django.db import models
from django.utils.timezone import now
from djmoney.models.fields import MoneyField

from properly.api import API
from rentals.models import Building
from reservations.models import Reservation
from util.rm_old import RmOldManager
from util.html_status_codes import get_json


class Cleaner(models.Model):
  name = models.CharField(max_length=200)
  # Do I need phone and email? Waiting to hear back from Properly.
  phone = models.CharField(max_length=50)
  email = models.CharField(max_length=100)
  hourly_rate = MoneyField(
      max_digits=10, decimal_places=2, default_currency='USD')
  buildings = models.ManyToManyField(Building)


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
        'AND res.check_in >= %s '
        'AND res.check_in < %s '
        'ORDER BY res.check_in;',
        [now(), now() + timedelta(days=7)])

  def create_job_requests(self, api=API()):
    return [self.create_job_request(
        res, api=api) for res in self.require_cleanings()]

  def create_job_request(self, reservation, api=API()):
    if self.filter(reservation=reservation).first():
      raise Exception('This job request was created already.')
    cleaning = Cleaning.objects.create(
        offered_to=self.available_cleaners(reservation),
        reservation=reservation)
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

  def create_job_request(self, api=API()):
    created_json = get_json(api.job_request_create(self._create_job_data()))
    print(created_json)  # DO NOT SUBMIT This is just until I snag an example.
    if created_json:
      self.creation_confirmed = now()
      self.job_request_id = created_json[
          'jobRequest.create'][0]['jobRequestId']
      self.save()

  def update_cleaners(self, api=API()):
    api.job_request_update(self._update_cleaners_data())

  def _create_job_data(self):
    start_time = self.reservation.check_out
    return {
        'sourceBookingId': '???',
        'receiveUpdates': True,
        'time': {
            'type': '???',
            'startTime': start_time.isoformat().replace('+00:00', '.000Z')},
        'property': {'sourcePropertyId': '???'},
        'checklists': [{'checklistId': '???'}],
        'serviceProviders': self._get_service_providers()}

  def _update_cleaners_data(self):
    return {
        'jobRequestId': self.job_request_id,
        'changes': {
            'receiveUpdates': True,
            'serviceProviders': self._get_service_providers()}}

  def _get_service_providers(self):
    service_providers = []
    for cleaner in self.offered_to:
      service_providers.append({'email': cleaner.email})


class RawEvent(models.Model):
  json = models.TextField(help_text='The raw json string from the request.')
  created_at = models.DateTimeField(auto_now_add=True, db_index=True)
  handled_at = models.DateTimeField(null=True, blank=True)

  objects = RmOldManager()
