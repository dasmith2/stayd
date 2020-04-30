from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.dispatch import receiver
from django.shortcuts import reverse

from commands.models import background_command
from errors.models import log_error, Notifier, notify, ErrorLogger
from rentals.models import Rental
from work.api import API
from work.models.maintenance_checklist import get_checklist_id_from_url
from work.models.rental import ProperlyRental
from work.models.sla import NEXT_CHECKOUT, NEXT_VACANT_NIGHT
from work.models.ticket import Ticket, REGULAR_MAINTENANCE
from work.models.work import Work, WorkManager
from work.models.work_type import WorkType
from reservations.models import Reservation
from util.fields import OneToOneOrNoneField
from util.signals import post_sync
from util.timezone import now, tz_dt_to_str


@receiver(post_sync, sender=Reservation)
def alert_or_cancel_if_overlap(sender, instance, *args, **kwargs):
  notifier = kwargs.get('notifier', Notifier())
  api = kwargs.get('api', API())
  scheduling_api = kwargs.get('scheduling_api', None)
  for overlap in RepeatWork.objects.get_overlap(instance):
    if overlap.accepted_by:
      subject = 'Regularly scheduled maintenance overlaps with reservation'
      message = (
          '{}\nYou can safely cancel the maintenance in Properly at '
          'https://app.getproperly.com/#/calendar?_k=kitpls').format(
              instance.admin_url())
      notifier.notify('tasks@stayd.com', subject, message)
      log_error(
          'Make sure its not my fault this res overlaps with maintenance',
          'res {} maintenance {}'.format(instance.pk, overlap.pk))
    else:
      overlap.cancel(
          'A reservation occured before this job was accepted', api,
          scheduling_api=scheduling_api)


@background_command
def create_tickets_background(nnow=None, scheduling_api=None):
  nnow = nnow or now()
  tickets = []
  for config in RepeatConfig.objects.filter(active=True):
    if config.can_create_ticket(nnow):
      tickets.append(config.create_ticket())
  return tickets


@background_command
def alert_should_have_but_didnt_unblock_background(
    scheduling_api=None, error_logger=None, nnow=None):
  """ This goes away with RepeatWork.

  One time, mckay reported that some canceled repeat work didn't unblock. So I
  wrote this double check here. """
  error_logger = error_logger or ErrorLogger()
  nnow = nnow or now()
  for work in RepeatWork.objects.filter(
      canceled_at__isnull=False,
      repeat_config__vacant_night_required=True,
      offered_start_time__gte=nnow - timedelta(days=2)).order_by(
          '-offered_start_time'):
    on_date = work.offered_start_time.date()
    if work.get_rental().is_blocked(on_date, api=scheduling_api):
      error_logger.log_error(
          'Canceled repeat work didn\'t unblock!',
          '{} {}'.format(work.pk, work), always_new_error=True)


class RepeatConfig(models.Model):
  """ This is the configuration for regularly scheduled maintenance. """
  title = models.CharField(max_length=200)
  properly_rental = models.ForeignKey(ProperlyRental, on_delete=models.CASCADE)
  rental = models.ForeignKey(
      Rental, null=True, blank=True, on_delete=models.CASCADE, help_text=(
          'Replacement for properly_rental'))
  work_type = models.ForeignKey(WorkType, on_delete=models.CASCADE)
  checklist_link = models.CharField(max_length=200, help_text=(
      'Literally copy and paste the properly URL for the checklist. e.g. '
      'https://app.getproperly.com/#/checklists/DYCB3hlT21/U3ZEGle9vt/'))
  days_between_jobs = models.PositiveIntegerField(help_text=(
      'How long should we wait before scheduling another one? Note that '
      'it\'ll typically be a bit longer than this if a vacant night is '
      'required.'))
  very_first_job = models.DateField(help_text=(
      'When should we try to schedule the very first instance of this work?'))
  expected_duration = models.PositiveIntegerField(default=3, help_text=(
      'How long do you expect this job to take (in hours)?'))
  vacant_night_required = models.BooleanField(help_text=(
      'Must this work be followed by a vacant night? For instance you '
      'wouldn\'t want a reservation immediately after a painting due '
      'to the smell.'))
  active = models.BooleanField(default=True, help_text=(
      'Never delete one of these after its put in use. Simply deactivate it.'))

  def save(self, *args, **kwargs):
    self.rental = self.properly_rental.rental
    super().save(*args, **kwargs)

  def url(self):
    return reverse('admin:work_repeatconfig_change', args=(self.pk,))

  def clean(self):
    super().clean()
    if not get_checklist_id_from_url(self.checklist_link):
      raise ValidationError(
          '{} doesnt appear to be a valid checklist link'.format(
              self.checklist_link))

  def can_create_ticket(self, nnow=None):
    return not self.explain_why_cant_create_ticket(nnow=nnow)

  def create_ticket(self):
    sla = NEXT_CHECKOUT
    if self.vacant_night_required:
      sla = NEXT_VACANT_NIGHT
    ticket = Ticket.objects.create(
        title=self.title,
        rental=self.properly_rental.rental,
        sla=sla,
        expected_duration=self.expected_duration,
        existing_checklist_url=self.checklist_link,
        work_type=self.work_type,
        came_from=REGULAR_MAINTENANCE)
    RepeatTicket.objects.create(ticket=ticket, config=self)
    return ticket

  def explain_why_cant_create_ticket(self, nnow=None):
    nnow = nnow or now()
    if not self.active:
      return 'This config is inactive'
    if not self._get_checklist_id():
      return 'The checklist_link is invalid'
    if nnow.date() < self.very_first_job:
      return 'The very first ticket shouldnt go out until {}'.format(
          self.very_first_job)
    earliest = self._get_earliest_time_given_last_complete_ticket()
    if earliest and nnow < earliest:
      return (
          'Given the last time this was done, the earliest the next '
          'ticket can go out is {}').format(tz_dt_to_str(earliest))
    if self.upcoming_ticket_exists(nnow):
      return 'There\'s already an upcoming ticket'

  def upcoming_ticket_exists(self, nnow=None):
    nnow = nnow or now()
    not_scheduled = Q(ticket__maintenance__isnull=True)
    # The service provider could start a few hours late.
    twelve_ago = nnow - timedelta(hours=12)
    future_scheduled = Q(
        ticket__maintenance__offered_start_time__gte=twelve_ago)
    in_progress = Q(
        ticket__completed_at__isnull=True,
        ticket__maintenance__started_at__gte=nnow - timedelta(days=1),
        ticket__maintenance__canceled_at__isnull=True,
        ticket__maintenance__completed_at__isnull=True)
    return self.repeatticket_set.filter(
        not_scheduled | future_scheduled | in_progress).exists()

  def get_last_complete_ticket(self):
    repeat_ticket = self.repeatticket_set.filter(
        ticket__completed_at__isnull=False).order_by(
            '-ticket__completed_at').first()
    if repeat_ticket:
      return repeat_ticket.ticket

  def _get_earliest_time_given_last_complete_ticket(self):
    latest = self.get_last_complete_ticket()
    if latest:
      return latest.completed_at + timedelta(
          days=self.days_between_jobs)

  def _get_checklist_id(self):
    checklist_id = get_checklist_id_from_url(self.checklist_link)
    if checklist_id:
      return checklist_id


class RepeatTicket(models.Model):
  ticket = OneToOneOrNoneField(Ticket, on_delete=models.CASCADE)
  config = models.ForeignKey(RepeatConfig, on_delete=models.CASCADE)


class RepeatWorkManager(WorkManager):
  def get_overlap(self, reservation):
    if reservation.canceled():
      return RepeatWork.objects.none()
    vacant_night_before_checkin = Q(
        repeat_config__vacant_night_required=True,
        offered_start_time__date=reservation.check_in.date())
    inside_reservation = Q(
        offered_start_time__gt=reservation.check_in,
        offered_start_time__lt=reservation.check_out)
    return RepeatWork.objects.filter(
        vacant_night_before_checkin | inside_reservation,
        repeat_config__properly_rental__rental=reservation.rental,
        canceled_at__isnull=True)


class RepeatWork(Work):
  """ This is for individual instances of regularly scheduled maintenance.
  This class is moribund. It's been replaced by tickets and maintenance jobs.
  """
  repeat_config = models.ForeignKey(RepeatConfig, on_delete=models.PROTECT)

  objects = RepeatWorkManager()

  def get_rental(self):
    return self.repeat_config.properly_rental.rental

  def invoice_prefix(self):
    return 'rw'

  def copy_to_ticket(self):
    if self.canceled_at:
      return True
    if not self.completed_at:
      return False
    sla = NEXT_CHECKOUT
    if self.repeat_config.vacant_night_required:
      sla = NEXT_VACANT_NIGHT
    ticket, created = Ticket.objects.get_or_create(
        title=self.repeat_config.title,
        rental=self.repeat_config.properly_rental.rental,
        sla=sla,
        expected_duration=self.repeat_config.expected_duration,
        existing_checklist_url=self.repeat_config.checklist_link,
        external_id=str(self.pk),
        work_type=self.repeat_config.work_type,
        completed_at=self.completed_at)
    if created:
      RepeatTicket.objects.get_or_create(
          ticket=ticket,
          config=self.repeat_config)
      Ticket.objects.filter(pk=ticket.pk).update(created_at=self.created_at)
      ticket.refresh_from_db()
    ticket.came_from = REGULAR_MAINTENANCE
    ticket.save()
    return True

  def reschedule(self, api, nnow=None, **kwargs):
    if self.offered_start_time > nnow:
      self.set_offered_to()
      if not self.offered_to.count():
        self.notify_cant_reschedule_no_service_providers()
    else:
      if not self.repeat_config.schedule():
        notify(
            self.alerts_email(),
            'Regularly scheduled maintenance canceled, unable to reschedule',
            self.url())

  def should_offer_to(self):
    return self.repeat_config.available_workers(self.offered_start_time)

  def url(self):
    return reverse('repeat_work_history_detail', kwargs={'pk': self.pk})

  def get_expected_duration(self):
    return self.repeat_config.expected_duration

  def get_deadline(self):
    raise Exception(
        'I believe maintenance should always be fixed and therefore '
        'get_deadline should never get called.')

  def alert_unaccepted_late_start(self):
    return False

  def get_source_property_id(self):
    return self.repeat_config.properly_rental.get_source_property_id()

  def get_properly_checklist_ids(self, api=None):
    return self.repeat_config.get_properly_checklist_ids()

  def get_message(self):
    return ''

  def get_title(self):
    return self.repeat_config.title

  def get_readable_work_title(self):
    return self.repeat_config.title

  def was_canceled(
      self, permanently_canceled_reason, scheduling_api=None, **kwargs):
    """ Blocking happens in set_accepted_by, unblocking in was_canceled. """
    super().was_canceled(
        permanently_canceled_reason, **kwargs)
    if self.repeat_config.vacant_night_required and self.accepted_by:
      self.get_rental().unblock(self.offered_start_time.date(), scheduling_api)

  def set_accepted_by(self, worker, scheduling_api=None):
    """ Blocking happens in set_accepted_by, unblocking in was_canceled. """
    super().set_accepted_by(worker)
    if self.repeat_config.vacant_night_required:
      self.repeat_config.properly_rental.rental.block(
          self.offered_start_time, 'Vacant night required for maintenance',
          scheduling_api)

  def __repr__(self):
    return '<RepeatWork {}: {}>'.format(self.pk, self.__str__())
