""" Cleaner inspection module. Unlike regularly scheduled maintenance which is
concerned with maintaining individual units, cleaning inspections are concerned
with maintaining the performance of individual cleaners. """
from datetime import timedelta

from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.shortcuts import reverse

from commands.models import background_command
from errors.models import log_error
from work.api import API
from work.models.cleaning import Cleaning
from work.models.work import Work, WorkManager
from work.models.worker import IndependentWorker, Worker
from work.models.work_type import WorkType, CLEANER, CLEANING_INSPECTOR
from typeform.models import (
    TypeForm, Response as TypeformResponse, STRING_ANSWER, INT_ANSWER)
from util.fields import OneToOneOrNoneField
from util.signals import post_sync
from util.timezone import now


@background_command
def schedule_inspections_background():
  Inspection.objects.schedule()


def get_cleaner_report(cleaner):
  last_5_inspections = Inspection.objects.for_cleaner(cleaner)[:5]
  average_score = 0
  overall_score = 0
  bathroom_score = 0
  kitchen_score = 0
  living_room_score = 0
  bedroom_score = 0

  overall_specifics = {}
  bathroom_specifics = {}
  kitchen_specifics = {}
  living_room_specifics = {}
  bedroom_specifics = {}

  for inspect in last_5_inspections:
    average_score += inspect.get_score()
    overall_score += inspect.get_overall_score()
    bathroom_score += inspect.get_bathroom_score()
    kitchen_score += inspect.get_kitchen_score()
    living_room_score += inspect.get_living_room_score()
    bedroom_score += inspect.get_bedroom_score()

    _extend_specifics(overall_specifics, inspect.get_overall_specifics())
    _extend_specifics(bathroom_specifics, inspect.get_bathroom_specifics())
    _extend_specifics(kitchen_specifics, inspect.get_kitchen_specifics())
    _extend_specifics(
        living_room_specifics, inspect.get_living_room_specifics())
    _extend_specifics(bedroom_specifics, inspect.get_bedroom_specifics())

  if last_5_inspections:
    average_score /= len(last_5_inspections)
    overall_score /= len(last_5_inspections)
    bathroom_score /= len(last_5_inspections)
    kitchen_score /= len(last_5_inspections)
    living_room_score /= len(last_5_inspections)
    bedroom_score /= len(last_5_inspections)

  last_5_cleanings = Cleaning.objects.filter(
      accepted_by=cleaner, completed_at__isnull=False).order_by(
          '-offered_start_time')[:5]
  on_time = 0
  all_tasks = 0
  for cleaning in last_5_cleanings:
    if cleaning.late_start() < timedelta(minutes=5):
      on_time += 1
    if cleaning.all_tasks_complete:
      all_tasks += 1

  return {
      'inspection_count': len(last_5_inspections),
      'last_5_inspections': list(last_5_inspections),
      'avg_total_score': average_score,
      'overall_score': overall_score,
      'overall_specifics': _get_top_3_specifics(overall_specifics),
      'bathroom_score': bathroom_score,
      'bathroom_specifics': _get_top_3_specifics(bathroom_specifics),
      'kitchen_score': kitchen_score,
      'kitchen_specifics': _get_top_3_specifics(kitchen_specifics),
      'living_room_score': living_room_score,
      'living_room_specifics': _get_top_3_specifics(living_room_specifics),
      'bedroom_score': bedroom_score,
      'bedroom_specifics': _get_top_3_specifics(bedroom_specifics),
      'cleaning_count': len(last_5_cleanings),
      'started_on_time': on_time,
      'all_tasks': all_tasks}


def _extend_specifics(specifics_lookup, specifics):
  for specific in specifics:
    if specific not in specifics_lookup:
      specifics_lookup[specific] = 0
    specifics_lookup[specific] += 1


def _get_top_3_specifics(specifics_lookup):
  # Sort first by count descending, but then by text alphabetically just to
  # make tests deterministic.
  top_3 = list(sorted(
      specifics_lookup.items(), key=lambda x: (-x[1], x[0])))[:3]
  return ', '.join('{} ({})'.format(top[0], top[1]) for top in top_3)


def get_inspection_typeform_id():
  typeform = TypeForm.objects.filter(
      title__icontains='cleaning inspection').first()
  if typeform:
    return typeform.typeform_id
  log_error(
      'Not sure what typeform is for cleaning inspections', (
          'Im looking for a TypeForm whose title contains the text '
          '"cleaning inspection". Because I couldnt find one I just went '
          'with the default id of Jh1K4F'))
  return 'Jh1K4F'


INSPECTIONS_START_AFTER_CLEANING = timedelta(minutes=45)
SCHEDULE_INSPECTIONS_DAYS_IN_ADVANCE = 5


class NeedsInspectionScoreManager(models.Manager):
  def assign_scores(self, nnow=None):
    nnow = nnow or now()
    for cleaner in Worker.objects.filter(
        work_types=WorkType.objects.get_work_type(CLEANER)):
      needs_inspection_score_obj = NeedsInspectionScore.objects.filter(
          cleaner=cleaner).first()
      if not needs_inspection_score_obj:
        needs_inspection_score_obj = NeedsInspectionScore(cleaner=cleaner)
      needs_inspection_score_obj.score = self._get_needs_inspection_score(
          cleaner, nnow)
      needs_inspection_score_obj.save()

  def _get_needs_inspection_score(self, worker, nnow):
    last_inspection = self._get_last_inspection(worker)
    if last_inspection is None:
      return 2000000
    if last_inspection.offered_start_time.date() >= nnow.date():
      return 0
    last_score = last_inspection.get_score()
    cleanings_since = self._cleanings_since(
        worker, last_inspection.offered_start_time)
    next_score = round(cleanings_since / (last_score ** 4))
    if cleanings_since >= 12:
      next_score += 1000000
    return next_score

  def _get_last_inspection(self, worker):
    return Inspection.objects.filter(
        inspect_cleaning__accepted_by=worker).order_by(
            '-offered_start_time').first()

  def _cleanings_since(self, worker, since):
    return Cleaning.objects.filter(
        accepted_by=worker,
        completed_at__isnull=False,
        offered_start_time__gt=since).count()


class NeedsInspectionScore(models.Model):
  """ Every cleaner should have a NeedsInspectionScore which simply says who is
  most in need of a cleaning inspection. The higher the score, the sooner
  you'll get inspected. Not to be confused with Inspection.score, which is the
  score for the cleaning. """
  cleaner = OneToOneOrNoneField(Worker, on_delete=models.CASCADE, help_text=(
      'The cleaner whose score this is.'))
  score = models.PositiveIntegerField(help_text=(
      'The higher the score, the sooner you\'ll get inspected.'))

  objects = NeedsInspectionScoreManager()

  class Meta:
    ordering = ('-score',)


class InspectionManager(WorkManager):
  def for_cleaner(self, cleaner):
    return self.filter(
        inspect_cleaning__accepted_by=cleaner,
        response__isnull=False).order_by(
            '-inspect_cleaning__offered_start_time')

  def _schedule_inspections_on(self, nnow=None):
    nnow = nnow or now()
    return nnow.date() + timedelta(
        days=SCHEDULE_INSPECTIONS_DAYS_IN_ADVANCE)

  def schedule(self, nnow=None, api=None):
    nnow = nnow or now()
    api = api or API()

    NeedsInspectionScore.objects.assign_scores(nnow=nnow)
    created = []
    for needs in NeedsInspectionScore.objects.filter(
        score__gt=0).order_by('-score'):
      cleaning = Cleaning.objects.filter(
          accepted_by=needs.cleaner,
          offered_start_time__date=self._schedule_inspections_on(nnow),
          canceled_at__isnull=True).first()
      if cleaning and self.get_inspection_checklist_id(cleaning):
        available_inspectors = self.get_available_inspectors(cleaning)
        if available_inspectors:
          created.append(self.create_job(
              cleaning, available_inspectors, nnow=nnow))
    return created

  def get_inspection_checklist_id(self, cleaning):
    config = cleaning.get_config()
    return config and config.inspection_checklist_id

  def get_available_inspectors(self, cleaning):
    start_time = self.get_start_time(cleaning)
    building_inspectors = IndependentWorker.objects.available(
        start_time, self.get_expected_duration(cleaning),
        cleaning.reservation.rental.building, CLEANING_INSPECTOR)
    # You can't inspect your own cleaning.
    cleaner = cleaning.accepted_by
    inspectors = []
    for inspector in set(building_inspectors) - set([cleaner]):
      # If Bob REALLY needs an inspection and Jane doesn't really, we want to
      # avoid allowing anybody to accept an inspection for Jane until we get an
      # inspection going for Bob. So you can't have an open offer for a
      # cleaning inspection on that day.
      open_offers = self.filter(
          offered_to=inspector,
          accepted_by__isnull=True,
          offered_start_time__date=start_time.date())
      if not open_offers.exists():
        inspectors.append(inspector)
    return inspectors

  def get_start_time(self, cleaning):
    return cleaning.get_start_time() + timedelta(
        hours=cleaning.get_expected_duration()) + (
            INSPECTIONS_START_AFTER_CLEANING)

  def get_expected_duration(self, cleaning):
    return 1

  def create_job(self, cleaning, offered_to, nnow=None):
    inspection = self.create(
        inspect_cleaning=cleaning,
        offered_start_time=self.get_start_time(cleaning))
    inspection.offered_to.set(offered_to)
    return inspection


@receiver(post_sync, sender=TypeformResponse)
def post_sync_response_inspection(sender, instance, *args, **kwargs):
  if instance.typeform.typeform_id == get_inspection_typeform_id():
    hiddens = instance.get_hidden_lookup()
    inspection = Inspection.objects.filter(
        inspect_cleaning__reservation__channel_id=hiddens[
            'reservation_id']).first()
    if inspection:
      inspection.response = instance
      inspection.save()


@receiver(post_save, sender=Cleaning)
def post_save_cleaning(sender, instance, *args, **kwargs):
  if instance.canceled_at:
    inspection = Inspection.objects.filter(inspect_cleaning=instance).first()
    if inspection:
      inspection.cancel('The cleaning is canceled.')


class Inspection(Work):
  inspect_cleaning = models.ForeignKey(
      Cleaning, on_delete=models.PROTECT, help_text=(
          'Which cleaning gets inspected?'))
  response = models.ForeignKey(
      TypeformResponse, on_delete=models.PROTECT, null=True, blank=True,
      help_text=(
          'The actual filled out description of how good the cleaning was.'))

  objects = InspectionManager()

  def invoice_prefix(self):
    return 'ins'

  def get_overall_score(self):
    # Walk through the entire apartment and rate the overall cleaning.
    return self._get_area_score('overall')

  def get_bathroom_score(self):
    # Rate the bathroom cleaning.
    return self._get_area_score('bathroom')

  def get_kitchen_score(self):
    # Rate the kitchen cleaning
    return self._get_area_score('kitchen')

  def get_living_room_score(self):
    # Rate the living room and common areas cleaning
    return self._get_area_score('living room')

  def get_bedroom_score(self):
    # Rate the bedroom cleaning
    return self._get_area_score('bedroom')

  def get_overall_specifics(self):
    return self._get_area_specifics('final')

  def get_bathroom_specifics(self):
    return self._get_area_specifics('bathroom')

  def get_kitchen_specifics(self):
    return self._get_area_specifics('kitchen')

  def get_living_room_specifics(self):
    return self._get_area_specifics('living room')

  def get_bedroom_specifics(self):
    return self._get_area_specifics('bedroom')

  def _get_area_score(self, area):
    return self.response.answer_set.filter(
        answer_type=INT_ANSWER,
        question__title__icontains=area).first().get_answer()

  def _get_area_specifics(self, area):
    answers = self.response.answer_set.filter(
        answer_type=STRING_ANSWER,
        question__title__icontains=area)
    return [answer.get_answer() for answer in answers]

  def get_score(self):
    # Innocent until proven guilty. This could happen if an inspector fails to
    # submit a score. Returns between 0 and 1.
    return (self.response and self.response.score / 100.0) or 1.0

  def get_score_percent(self):
    # Returns between 0 and 100.
    return int(100 * self.get_score())

  def get_rental(self):
    return self.inspect_cleaning.get_rental()

  def reschedule(self, api, **kwargs):
    pass

  def url(self):
    return reverse('admin:work_inspection_change', args=(self.pk,))

  def get_expected_duration(self):
    return Inspection.objects.get_expected_duration(self.inspect_cleaning)

  def get_start_time(self):
    return Inspection.objects.get_start_time(self.inspect_cleaning)

  def get_deadline(self):
    raise Exception(
        'I believe cleaning inspections should always be fixed and therefore '
        'get_deadline should never get called.')

  def alert_unaccepted_late_start(self):
    return False

  def get_source_property_id(self):
    return self.inspect_cleaning.get_source_property_id()

  def get_properly_checklist_ids(self, api=None):
    inspection_id = Inspection.objects.get_inspection_checklist_id(
        self.inspect_cleaning)
    if inspection_id:
      return [inspection_id]
    raise Exception((
        'Cant create inspection for {} without a cleaning inspection '
        'checklist.').format(self.inspect_cleaning.get_rental()))

  def get_message(self):
    return 'https://stayd.typeform.com/to/{}?reservation_id={}'.format(
        get_inspection_typeform_id(),
        self.inspect_cleaning.reservation.channel_id)

  def get_source_booking_id(self):
    return self.inspect_cleaning.get_source_booking_id()

  def get_title(self):
    return 'Inspection'

  def get_readable_work_title(self):
    return 'a cleaning inspection'

  def __repr__(self):
    return '<Inspection {}: {}>'.format(self.pk, self.__str__())
