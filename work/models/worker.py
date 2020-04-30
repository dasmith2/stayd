from abc import abstractmethod

from django.contrib.auth.models import User
from django.dispatch import receiver
from django.db import models
from django.db.models import Q
from django.db.models.signals import post_save
from django.shortcuts import reverse
from djmoney.models.fields import MoneyField

from work.models.fixed_or_flexible import FIXED, FLEXIBLE
from work.models.work_type import WorkType, CLEANER
from rentals.models import Building
from util.fields import OneToOneOrNoneField
from util.object_lookup import get_pairs
from util.phone import numbers_only
from util.urls import admin_edit_url


def all_active_workers():
  work_co_worker_active = Q(
      workcoworker__active_by_cleaning_company=True,
      workcoworker__active=True)
  indep_worker = Q(independentworker__buildings__isnull=False)
  return Worker.objects.filter(
      work_co_worker_active | indep_worker).distinct()


class Worker(models.Model):
  worker_id = models.CharField(
      max_length=200, null=True, blank=True, help_text=(
          'This comes from jobRequest.accepted webhooks as serviceProviderId. '
          'The trick is matching ids to workers. You go to the Properly '
          'calendar and find out which worker actually did accept the job.'))
  name = models.CharField(max_length=200)
  phone = models.CharField(max_length=50, help_text=(
      'Please include a country code, for instance, +17198063264.'))
  # This should have unique=True as well.
  phone_numbers_only = models.CharField(
      max_length=50, null=True, help_text=(
          'This field has no formatting so its better for lookups.'))
  email = models.CharField(max_length=100, unique=True, help_text=(
      'We need this to set up jobs.'))
  # I guessed wrong when I put the user field on IndependentWorker because now
  # WorkCoWorkers will sign in to complete cleanings. So obviously the long
  # game here is remove IndependentWorker.user and rename Worker.base_user
  # user.
  base_user = OneToOneOrNoneField(
      User, on_delete=models.CASCADE, null=True, help_text=(
          'If this worker is going to log into work.hihoward.com or '
          'clean.hihoward.com, theyll need a username and password.'))

  # Cleaning inspections looks up workers by work type, and we want to inspect
  # both WorkCo and Independent workers. So I just automatically make all
  # WorkCoWorkers Cleaners.
  work_types = models.ManyToManyField(WorkType, blank=True)

  @abstractmethod
  def get_hour_min(self):
    raise NotImplementedError('get_hour_min')

  @abstractmethod
  def get_work_co(self):
    raise NotImplementedError('get_work_co')

  @abstractmethod
  def get_payment_email(self):
    raise NotImplementedError('get_payment_email')

  def is_cleaner(self):
    return self.work_types.filter(name=CLEANER).exists()

  def admin_edit_url(self):
    return admin_edit_url(self.get_child_class_instance())

  def cleaning_score_url(self):
    return reverse('cleaning_score', kwargs={'worker_pk': self.pk})

  def get_child_class_instance(self):
    if self.__class__ != Worker:
      # If you do select_related('worker__independentworker'), then
      # .worker.independentworker won't require an additional sql query. So far
      # so good. But if you do .worker.independentworker.independentworker, it
      # WILL require an additional SQL query.
      return self
    try:
      return self.independentworker
    except Worker.independentworker.RelatedObjectDoesNotExist:
      pass
    try:
      return self.workcoworker
    except Worker.workcoworker.RelatedObjectDoesNotExist:
      pass
    raise Exception()

  def __str__(self):
    return self.name

  def __repr__(self):
    return '<Worker {}: {} {} {}>'.format(
        self.pk, self.name, self.phone, self.email)

  class Meta:
    ordering = ('name',)
    # The easiest way to block duplicates on the work_co_worker page.
    unique_together = ('name', 'phone', 'email')


@receiver(post_save)
def post_save_worker(sender, instance, *args, **kwargs):
  # If you do a post save on Worker, it won't fire for IndependentWorker
  if isinstance(instance, Worker):
    nums_only = numbers_only(instance.phone)
    if instance.phone_numbers_only != nums_only:
      instance.phone_numbers_only = nums_only
      instance.save()


class IndependentWorkerManager(models.Manager):
  def should_offer_to(
      self, work_type, offered_to, building, fixed_or_flexible,
      offered_start_time, expected_duration):
    # This is used by one_off and ticket.
    if not work_type:
      return offered_to
    elif fixed_or_flexible == FIXED:
      return self.available(
          offered_start_time, expected_duration, building, work_type)
    elif fixed_or_flexible == FLEXIBLE:
      return self.for_building(building, work_type)
    else:
      raise Exception(fixed_or_flexible)

  def for_building(self, building, work_type):
    if isinstance(work_type, str):
      work_type = WorkType.objects.get(name=work_type)
    return self.filter(buildings=building, work_types=work_type)

  def available(self, at_time, duration, building, work_type):
    if isinstance(work_type, str):
      work_type = WorkType.objects.get_work_type(work_type)
    from work.models.work import Work
    # This comes back, like IndependentWorker, WorkCoWorker, ...
    all_building_workers = set(self.for_building(building, work_type))
    concurrent_work = Work.objects.concurrent(
        at_time, duration, all_building_workers, 'ACCEPTED')
    # work.accepted_by is the base class, Worker
    busy_worker_pks = set([work.accepted_by.pk for work in concurrent_work])
    to_return = []
    for worker in all_building_workers:
      if worker.pk not in busy_worker_pks:
        to_return.append(worker)
    return to_return

  def get_building_work_type_lookup(self):
    """ Return a dictionary of which work types are available per building
    given the independent workers that are configured for buildings and the
    work types they have.
    {building_1 -> set(work type 1, work type 2),
     building_2 -> set()} """
    query = """
        SELECT wkr_bld.building_id, wkr_wt.worktype_id
        FROM
        work_independentworker_buildings AS wkr_bld
        JOIN work_worker_work_types AS wkr_wt
        ON wkr_bld.independentworker_id = wkr_wt.worker_id;"""
    lookup = {}
    for building, work_type in get_pairs(query, Building, WorkType):
      if building not in lookup:
        lookup[building] = set()
      lookup[building].add(work_type)
    return lookup

  def get_building_worker_lookup(self):
    """ Return a dictionary of which independent workers are available per
    building given the independent workers that are configured for buildings.
    {building_1 -> set(worker_1, worker_2),
     building_2 -> set()}
    """
    query = """
        SELECT building_id, independentworker_id
        FROM work_independentworker_buildings;"""
    lookup = {}
    for building, worker in get_pairs(query, Building, IndependentWorker):
      if building not in lookup:
        lookup[building] = set()
      lookup[building].add(worker)
    return lookup


class IndependentWorker(Worker):
  hour_rate = MoneyField(
      max_digits=10, decimal_places=2, default_currency='USD')
  hour_min = models.PositiveIntegerField(default=1, help_text=(
      'For each job, pay for at least this many hours.'))
  buildings = models.ManyToManyField(Building, blank=True)
  full_time_employee = models.BooleanField(default=False, help_text=(
      'Be careful! This flag should only be turned on for actual full time '
      'employees. Do not turn this on for contractors or service providers '
      'because then we are liable for things like unemployment. If this is '
      'on, keys will create payments with the hour_rate, but those payments '
      'get status NOT_REQUIRED. So payments for this service provider will '
      'never get sent to the service provider, but nevertheless the amount '
      'of those payments will be available in reports to bill back to '
      'owners.'))

  objects = IndependentWorkerManager()

  def get_payment_email(self):
    return self.email

  def get_hour_min(self):
    return self.hour_min

  def get_work_co(self):
    return None

  class Meta:
    ordering = ('name',)

  def __repr__(self):
    return '<(Independent)Worker {}: {} {} {}>'.format(
        self.pk, self.name, self.phone, self.email)
