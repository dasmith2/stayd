""" These are finally no longer used! I would love to turn them all into
maintenance jobs or something and remove OneOff entirely. """
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.shortcuts import reverse

from commands.models import background_command
from rentals.models import Building, Rental
from work.api import API
from work.models.maintenance_checklist import (
    get_checklist_id_from_url, MaintenanceChecklist)
from work.models.fixed_or_flexible import FIXED, FLEXIBLE
from work.models.work import Work
from work.models.worker import IndependentWorker
from work.models.work_type import WorkType
from work.models.rental import ProperlyRental
from util.random_string import get_new_random_string
from util.timezone import now


@background_command
def disable_old_checklists_background(api=None, nnow=None):
  nnow = nnow or now()
  api = api or API()
  disabled = []
  # https://keys.hihoward.com/admin/work/oneoff/333/readonly/ doesn't
  # have a checklist because the checklist creation failed because it contains
  # a line item that's only got one character.
  # https://keys.hihoward.com/admin/work/oneoff/299/readonly/ doesn't
  # have a checklist because it has an existing_checklist_url
  for one_off in OneOff.objects.filter(
      offered_start_time__lte=nnow - timedelta(days=14),
      checklist__isnull=False, checklist__disabled_at__isnull=True):
    disabled.append(one_off.checklist.disable(api))
  return disabled


class OneOff(Work):
  title = models.CharField(max_length=200)
  message = models.CharField(max_length=500, help_text=(
      'Any additional details they\'ll need to know to perform this job.'),
      blank=True, default='')
  properly_rental = models.ForeignKey(
      ProperlyRental, on_delete=models.PROTECT, help_text=(
          'Where should the service provider arrive in order to do the work?'))
  rental = models.ForeignKey(
      Rental, on_delete=models.PROTECT, null=True, blank=True, help_text=(
          'Replacement for the properly_rental field'))
  work_type = models.ForeignKey(
      WorkType, blank=True, null=True, on_delete=models.PROTECT, help_text=(
          'WARNING: The point of this field is to overwrite "Offered to:" '
          'with service providers of this work type for this building.'))
  end_time = models.DateTimeField(blank=True, null=True, help_text=(
      'What time should the job be done by? This only applies to flexible.'))
  expected_duration = models.DecimalField(
      decimal_places=2, max_digits=5,
      help_text='How long do we expect this job to take in hours.')
  checklist = models.ForeignKey(
      MaintenanceChecklist, on_delete=models.PROTECT, blank=True, null=True)
  existing_checklist_url = models.CharField(
      max_length=200, null=True, blank=True, help_text=(
          'You may use an existing checklist instead of typing out a new one. '
          'Copy and paste the entire checklist url here. For example, '
          'https://app.getproperly.com/#/checklists/5c6f286a739846d03d7ac688'
          '/5c6f286bab0286c6b8dab6e6/'))
  bill_to_building = models.ForeignKey(
      Building, on_delete=models.PROTECT, null=True, blank=True, help_text=(
          'What building should this work get billed to, if different from '
          'the building implied by the properly_rental?'))

  def save(self, *args, **kwargs):
    self.rental = self.properly_rental.rental
    super().save(*args, **kwargs)
    if self.can_set_offered_to():
      self.set_offered_to()

  def invoice_prefix(self):
    return 'hm'

  def admin_url(self):
    return reverse('one_off_history_detail', kwargs={'pk': self.pk})

  def duplicate(self, nnow=None):
    nnow = nnow or now()
    new_offered_start_time = nnow
    new_end_time = None
    if self.end_time:
      new_end_time = new_offered_start_time + (
          self.end_time - self.offered_start_time)
    copied = OneOff.objects.create(
        title=self.title, message=self.message,
        properly_rental=self.properly_rental, work_type=self.work_type,
        end_time=new_end_time, offered_start_time=new_offered_start_time,
        expected_duration=self.expected_duration,
        existing_checklist_url=self.existing_checklist_url,
        fixed_or_flexible=self.fixed_or_flexible)
    if not self.work_type:
      copied.offered_to.set(self.offered_to.all())
    for line_item in self.lineitem_set.order_by('pk'):
      LineItem.objects.create(
          one_off=copied, description=line_item.description)
    return copied

  def get_readable_work_title(self):
    return self.title

  def troubling_creation_attempt_count(self):
    return 20

  def clean(self):
    super().clean()
    if self.fixed_or_flexible == FLEXIBLE and not self.end_time:
      raise ValidationError('end_time is required for FLEXIBLE jobs.')
    if self.existing_checklist_url and not get_checklist_id_from_url(
        self.existing_checklist_url):
      raise ValidationError(
          '{} doesnt appear to be a valid checklist url'.format(
              self.existing_checklist_url))

  def get_rental(self):
    return self.properly_rental.rental

  def get_bill_to_building(self):
    return self.bill_to_building or self.get_rental().building

  def reschedule(self, api=None, nnow=None, **kwargs):
    self.set_offered_to()
    if not self.offered_to.count():
      self.notify_cant_reschedule_no_service_providers()

  def should_offer_to(self):
    return IndependentWorker.objects.should_offer_to(
        self.work_type, self.offered_to.all(),
        self.properly_rental.rental.building, self.fixed_or_flexible,
        self.offered_start_time, self.get_expected_duration())

  def url(self):
    return reverse('admin:work_oneoff_change', args=(self.pk,))

  def get_readonly_admin_url(self):
    return reverse('one_off_history_detail', kwargs={'pk': self.pk})

  def get_expected_duration(self):
    return self.expected_duration

  def get_deadline(self):
    min_end_time = self.offered_start_time + timedelta(
        seconds=round(self.expected_duration * 3600))
    if self.end_time < min_end_time:
      self.end_time = min_end_time
      self.save()
    return self.end_time

  def alert_unaccepted_late_start(self):
    return False

  def get_source_property_id(self):
    return self.properly_rental.get_source_property_id()

  def get_properly_checklist_ids(self, api=None):
    api = api or API()
    if self.existing_checklist_url:
      return [get_checklist_id_from_url(self.existing_checklist_url)]
    return [self.create_checklist(api).checklist_id]

  def get_message(self):
    return self.message

  def get_title(self):
    return self.title

  def is_fixed(self):
    return self.fixed_or_flexible == FIXED

  def create_checklist(self, api):
    if not self.checklist:
      self.checklist = MaintenanceChecklist.objects.create(
          properly_rental=self.properly_rental,
          title=self.title,
          description=self.message)
      for task in self.lineitem_set.all():
        self.checklist.add_task(task.description)
    if not self.checklist.checklist_id:
      self.checklist.create_checklist(api)
    return self.checklist

  def __repr__(self):
    return '<OneOff {}: {}>'.format(self.pk, self.__str__())


class LineItem(models.Model):
  one_off = models.ForeignKey(OneOff, on_delete=models.CASCADE)
  description = models.CharField(max_length=300)

  class Meta:
    # Without this, the default seems to be reverse pk, so the checklists were
    # being created in reverse order!
    ordering = ('pk',)


def get_new_unique_prefix():
  """ This was the old default for unique_prefix. Django migrations freaks out
  if I remove it. """
  return get_new_random_string()
