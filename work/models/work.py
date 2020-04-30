""" This is the shared stuff between different types of work such as cleaning
and maintenance. """
from collections import namedtuple
from datetime import timedelta
import re

from django.conf import settings
from django.db import models

from errors.models import log_error, notify
from work.api import API, SERVER_ERROR
from work.models.fixed_or_flexible import (
    FIXED, FLEXIBLE, FIXED_FLEXIBLE_CHOICES)
from work.models.rental import properly_datetime_format
from work.models.worker import Worker
from util.timezone import (
    get_readable_duration, tz_dt_to_abbr_str, now, tz_dt_to_tz_dt)
from util.urls import keys_url


NOT_CREATED = 'NOT_CREATED'
CREATED = 'CREATED'
CREATING = 'CREATING'
OFFERED = 'OFFERED'
ACCEPTED = 'ACCEPTED'
STARTED = 'STARTED'
COMPLETE = 'COMPLETE'
PAID = 'PAID'
CANCELED = 'CANCELED'
CREATION_ERROR = 'CREATION_ERROR'


HoursAndPayRow = namedtuple(
    'HoursAndPayRow',
    'worker_name jobs hours hour_rate total_earnings')


def remove_canceled_or_declined(work, worker_list):
  if not work:
    return worker_list
  remove_these = set(
      [worker.pk for worker in work.get_canceled_or_declined_workers()])
  return [worker for worker in worker_list if worker.pk not in remove_these]


class WorkManager(models.Manager):
  def concurrent(self, at_time, duration, workers, accepted_or_offered):
    """ accepted_or_offered is either 'OFFERED' or 'ACCEPTED'. If you're
    concerned about the concurrent work for a specific job, don't use this
    function directly. Use my_work.overlapping() """
    existing_work = []
    to_time = at_time + timedelta(seconds=int(duration * 3600))
    # We don't do overlap checks for FLEXIBLE jobs.
    jobs = Work.objects.filter(
        offered_start_time__lt=to_time,
        offered_start_time__date=at_time.date(),
        fixed_or_flexible=FIXED, canceled_at__isnull=True)
    if accepted_or_offered == 'ACCEPTED':
      jobs = jobs.filter(accepted_by__in=workers)
    elif accepted_or_offered == 'OFFERED':
      jobs = jobs.filter(offered_to__in=workers, accepted_by__isnull=True)
    else:
      raise Exception(accepted_or_offered)
    for possible in jobs:
      possible = possible.get_child_class_instance()
      if at_time < possible.get_expected_done_by():
        existing_work.append(possible)
    return existing_work

  def todays_jobs(self, nnow=None):
    nnow = nnow or now()
    filters = {
        'offered_start_time__date': nnow.date(), 'canceled_at__isnull': True}
    if self.__class__ is WorkManager:
      jobs = self.filter(**filters).select_related(
          'cleaning', 'oneoff', 'repeatwork', 'inspection', 'accepted_by')
      return [job.get_child_class_instance() for job in jobs]
    # So if this is actually the CleaningManager which inherits from
    # WorkManager, it'll do Cleaning.objects.filter...
    return self.filter(**filters).select_related('accepted_by')


class Work(models.Model):
  """ I wish I'd called this class Job in retrospect. """
  offered_to = models.ManyToManyField(
      Worker, related_name='offered_to', blank=True, help_text=(
          'Who can see this job offer in their Properly app? This will be '
          'overwritten by one-offs with a work type!'))
  # For cleanings in keys, accepted_by sets when the cleaning is started. So in
  # that case, you could theoretically replace accepted_by and offered_to with
  # a single assigned_to field. But when it comes to maintenance, we often have
  # multiple workers working different days, so we'll offer the job to both and
  # whoever is working that day accepts it. So let's keep this distinction of
  # accepted_by and offered_to in the base class because it does work for
  # cleanings and maintenance.
  accepted_by = models.ForeignKey(
      Worker, related_name='accepted_by', on_delete=models.CASCADE,
      null=True, blank=True, help_text='Who actually took the job?')

  # Note that unlike properly bookings and properties, jobs don't have a
  # source_job_request_id for some reason.
  job_request_id = models.CharField(
      max_length=100, default='', db_index=True, help_text=(
          'This comes back in the response to the create_job request. You '
          'need it to create an update request.'))

  created_at = models.DateTimeField(
      auto_now_add=True, db_index=True, help_text=(
          'When was this object created. See creation_confirmed for when '
          'the job actually got created in Properly.'))
  creation_started = models.DateTimeField(null=True, blank=True, help_text=(
      'These get created in the background. I need a way to communicate back '
      'to the web what happened.'))
  creation_confirmed = models.DateTimeField(null=True, blank=True, help_text=(
      'When did Properly send us a webhook confirming the successful creation '
      'of this job?'))
  creation_error = models.TextField(default='', help_text=(
      'These get created in the background. I need a way to communicate back '
      'to the web what happened.'))
  creation_attempts = models.PositiveIntegerField(default=0, help_text=(
      'How many times did we try to create this work?'))
  create_properly_job_client_request_id = models.CharField(
      max_length=50, null=True, blank=True, help_text=(
          'We keep track of the client_request_id for creating the job so if '
          'we get a webhook back with an error we can figure out what work '
          'its refering to, and possibly retry to create it.'))

  accepted_at = models.DateTimeField(null=True, blank=True)
  started_at = models.DateTimeField(null=True, blank=True)
  completed_at = models.DateTimeField(null=True, blank=True)
  offered_start_time = models.DateTimeField(db_index=True, help_text=(
      'THIS IS IN NEW YORK TIME!!!'))
  # OneOff has an end_time field which came first. Later I realized other forms
  # of work need that concept, which is what deadline is. When OneOff is
  # replaced by Maintenance and I remove OneOff, the situation will make sense.
  deadline = models.DateTimeField(null=True, blank=True, help_text=(
      'This only applies to flexibly scheduled jobs.'))
  fixed_or_flexible = models.CharField(
      max_length=20, choices=FIXED_FLEXIBLE_CHOICES, default=FIXED, help_text=(
          'Flexible jobs may overlap. Fixed jobs may not overlap. Fixed means '
          'you should start right away and be done in the '
          'expected duration. Flexible means you should just start after the '
          'offered start time and finish before the end time.'))
  canceled_at = models.DateTimeField(null=True, blank=True)
  permanently_canceled_reason = models.TextField(
      default='', blank=True, help_text=(
          'Explain why this one got permanently canceled'))
  all_tasks_complete = models.BooleanField(default=True)
  action_on_properly = models.BooleanField(default=False, help_text=(
      'Have we received any accepted, start, or complete events from properly '
      'for this job?'))
  action_on_keys = models.BooleanField(default=False, help_text=(
      'Have we received any start or complete events from keys for this job?'))
  action_on_keys_canceled_on_properly_at = models.DateTimeField(
      null=True, blank=True, help_text=(
          'If we see some action on keys we want to cancel on properly to '
          'avoid duplicating maintenance work.'))

  objects = WorkManager()

  def __str__(self):
    try:
      return '{} at {} on {}'.format(
          self.get_readable_work_title(), self.get_rental().nickname,
          self.offered_start_time.date())
    except NotImplementedError:
      return self.get_child_class_instance().__str__()

  def __repr__(self):
    return '<Work {}: {}>'.format(self.pk, self.__str__())

  def save(self, *args, **kwargs):
    if self.permanently_canceled_reason and not self.canceled_at:
      raise Exception(
          '{} has a permanently_canceled_reason but no canceled_at'.format(
              self.keys_url()))
    super().save(*args, **kwargs)

  def status(self):
    if self.canceled_at:
      return CANCELED
    if self.workpayment_or_none and self.workpayment.success():
      return PAID
    if self.completed_at:
      return COMPLETE
    if self.started_at:
      return STARTED
    if self.accepted_by:
      return ACCEPTED
    return CREATED

  def pretty_status(self):
    if self.status() == CANCELED:
      return 'canceled on {}'.format(self.canceled_at.date())
    accepted_by_name = (self.accepted_by and self.accepted_by.name) or '???'
    if self.status() == COMPLETE:
      if self.accepted_by:
        return 'completed by {} on {}'.format(
            self.accepted_by.name, self.completed_at.date())
      else:
        return 'marked complete on {}'.format(self.completed_at.date())
    if self.status() == STARTED:
      return 'started by {} at {}'.format(
          accepted_by_name, self.get_readable_time_str(self.started_at))
    if self.status() == ACCEPTED:
      return 'accepted by {} for {}'.format(
          accepted_by_name, self.offered_start_time.date())
    if self.status() == OFFERED:
      return 'offered to {} workers for {}'.format(
          self.offered_to.count(), self.offered_start_time.date())
    if self.status() == CREATED:
      return 'created at {}'.format(self.created_at.date())
    if self.status() == CREATION_ERROR:
      return 'creation error around {}'.format(
          tz_dt_to_abbr_str(self.creation_started))
    if self.status() == PAID:
      return PAID
    raise Exception(self.status())

  def select_related_child_classes(self, query):
    return query.select_related(
        'cleaning', 'repeatwork', 'oneoff', 'inspection')

  def get_child_class_instance(self):
    if self.__class__ != Work:
      # If you do select_related('work__cleaning'), then .work.cleaning won't
      # require an additional sql query. So far so good. But if you do
      # .work.cleaning.cleaning, it WILL require an additional SQL query.
      return self
    try:
      return self.cleaning
    except Work.cleaning.RelatedObjectDoesNotExist:
      pass
    try:
      return self.repeatwork
    except Work.repeatwork.RelatedObjectDoesNotExist:
      pass
    try:
      return self.oneoff
    except Work.oneoff.RelatedObjectDoesNotExist:
      pass
    try:
      return self.inspection
    except Work.inspection.RelatedObjectDoesNotExist:
      pass
    try:
      return self.maintenance
    except Work.maintenance.RelatedObjectDoesNotExist:
      pass
    # There is now a rare case when there is no child class instance. When
    # somebody creates a job via the web UI, we only hear about the job through
    # the listing.cleaningJobs API call, and we don't have enough information
    # to figure out what type of job it was.
    return self

  def invoice_prefix(self):
    raise NotImplementedError('invoice_prefix')

  def tax_rate(self):
    return 0

  def get_rental(self):
    raise NotImplementedError('get_rental')

  def get_bill_to_building(self):
    return self.get_rental().building

  def reschedule(self, api, **kwargs):
    raise NotImplementedError('reschedule')

  def get_local_time(self, tz_dt):
    return tz_dt_to_tz_dt(tz_dt, self.get_time_zone())

  def get_offered_start_time(self):
    return self.get_local_time(self.offered_start_time)

  def get_time_zone(self):
    return self.get_rental().building.time_zone

  def get_started_at(self):
    if self.started_at:
      return self.get_local_time(self.started_at)

  def get_completed_at(self):
    if self.completed_at:
      return self.get_local_time(self.completed_at)

  def uses_work_co(self):
    return False

  def get_work_co(self):
    return None

  def uses_independent_workers(self):
    return True

  def send_good_morning_todays_jobs_to(self):
    if self.accepted_by:
      return [self.accepted_by]
    return self.offered_to.all()

  def pay_who(self):
    if self.uses_work_co():
      return self.get_work_co()
    return self.accepted_by

  def url(self):
    raise NotImplementedError('url')

  def keys_url(self):
    return keys_url(self.url())

  def alerts_email(self):
    return self.get_rental().building.alerts_email

  def get_expected_duration(self):
    raise NotImplementedError('get_expected_duration')

  def create_properly_job_data(self, api=None, nnow=None):
    api = api or API()
    nnow = nnow or now()
    # Properly is picky about scheduling. The start time should be in the
    # future.
    if self.offered_start_time < nnow:
      if settings.TEST:
        raise Exception('You gotta pass in nnow')
      self.offered_start_time = nnow + timedelta(minutes=10)
      self.save()

    is_flexible = self.fixed_or_flexible == FLEXIBLE
    time = {
        'type': 'flexible' if is_flexible else 'fixed',
        'startTime': properly_datetime_format(self.get_start_time()),
        # Decimals aren't serializable for some reason. Easily my least
        # favorite data type.
        'durationInHours': float(self.get_expected_duration())}
    if is_flexible:
      if not self.get_deadline():
        raise Exception('Flexible jobs require a deadline.')
      time['endTime'] = properly_datetime_format(self.get_deadline())
      if self.deadline_minus_start_time_hours() < self.get_expected_duration():
        raise Exception((
            'get_expected_duration cant be more than '
            'get_deadline - get_start_time'), self.keys_url())
    checklists = []
    for checklist_id in self.get_properly_checklist_ids(api):
      checklists.append({'checklistId': checklist_id})
    data = {
        'title': self.get_title(),
        'receiveUpdates': True,  # Not really sure what this does.
        'time': time,
        'property': {'sourcePropertyId': self.get_source_property_id()},
        'checklists': checklists,
        'serviceProviders': self.get_service_provider_data()}
    if self.get_message():
      data['message'] = self.get_message()
    if self.get_source_booking_id():
      data['sourceBookingId'] = self.get_source_booking_id()
    return data

  def deadline_minus_start_time_hours(self):
    start = self.get_start_time()
    deadline = self.get_deadline()
    if not deadline:
      raise Exception((
          'Why are you asking about deadline_minus_start_time_hours when '
          'there is no deadline?'), self.keys_url())
    if deadline < start:
      raise Exception(
          '{} < {} for {}'.format(deadline, start, self.keys_url()))
    return (deadline - start).seconds / 3600

  def get_title(self):
    raise NotImplementedError('get_title')

  def get_readable_work_title(self):
    raise NotImplementedError('get_readable_work_title')

  def get_start_time(self):
    return self.offered_start_time

  def get_deadline(self):
    """ This only applies to FLEXIBLE jobs. """
    raise NotImplementedError('get_deadline')

  def alert_unaccepted_late_start(self):
    # If this job is unnaccepted and doesn't start on time, should we alert
    # somebody? For instance, cleanings, yes. Maintenance, nah.
    raise NotImplementedError('alert_unaccepted_late_start')

  def get_expected_done_by(self):
    if self.fixed_or_flexible == FLEXIBLE:
      return self.get_deadline()
    return self.offered_start_time + timedelta(
        minutes=round(60 * self.get_expected_duration()))

  def get_source_property_id(self):
    raise NotImplementedError('get_source_property_id')

  def get_properly_checklist_ids(self, api=None):
    raise NotImplementedError('get_properly_checklist_ids')

  def checklist_complete_on_properly(self, who_completed_it, checklist_id):
    """ Maintenance uses this to auto-mark tickets as complete. """
    pass

  def get_message(self):
    raise NotImplementedError('get_message')

  def get_source_booking_id(self):
    return None

  def should_offer_to(self):
    raise NotImplementedError('should_offer_to')

  def handle_server_error_in_create_webhook(self, message_sender):
    """ Ugh, one time this happened all day and the jobs actually did get
    created, but we didn't get webhooks for those jobs. But also at the time I
    wasn't distinguishing between

    'Invalid response from Parse. Expecting status 200 and received: '
    '400 - Body: ') <- Couldn't find an object
    'Invalid response from Parse. Expecting status 200 and received: '
    '503 - Body: ') <- Server error (what this function is for)

    So I'd coded it up to retry creation on a 503, and all of those actually
    created but returned errors and didn't have webhooks. So that was quite a
    mess.

    Then another time this happened and the job didn't get created. Since
    there's no way to tell if the job got created or not, I won't retry
    creation, and I'll notify. """
    # Crap, this circular dependency means I've structured something wrong.
    from work.models.message import Message, UNKNOWABLE_JOB_CREATION_ERROR
    self.creation_error = SERVER_ERROR
    self.save()
    content = (
        'Properly just threw a particularly unhelpful error when I tried to '
        'create this job: {} Due to the considerable '
        'limitations of the properly API, I don\'t know if this job was '
        'created or not. Could somebody please go check the Properly web '
        'interface?').format(keys_url(self.url()))
    Message.objects.create_and_send_email(
        to=self.alerts_email(),
        reason=UNKNOWABLE_JOB_CREATION_ERROR, content=content,
        work=self, message_sender=message_sender)
    return True

  def get_tz_dt(self, dt):
    # Why are timezones such a pain.
    return self.get_rental().building.set_timezone(dt)

  def get_readable_time_str(self, dt):
    """ 11:15am, 2:00pm """
    dt = self.get_tz_dt(dt)
    return re.sub('^0', '', dt.strftime('%I:%M%p').lower())

  def get_readable_date_time_str(self, dt):
    return self.get_tz_dt(dt).strftime('%Y-%m-%d %I:%M%p').lower()

  def get_full_start_time_str(self):
    return self.get_readable_date_time_str(self.offered_start_time)

  def get_address_and_time(self):
    address = self.get_rental().full_address
    return '{} {}'.format(
        address, self.get_readable_time_str(self.offered_start_time))

  def can_set_offered_to(self):
    return self.status() in [CREATED, OFFERED, CANCELED, CREATION_ERROR]

  def set_offered_to(self):
    if self.can_set_offered_to():
      existing = set(self.offered_to.all())
      should = set(remove_canceled_or_declined(self, self.should_offer_to()))
      for remove in existing - should:
        self.offered_to.remove(remove)
      for add in should - existing:
        self.offered_to.add(add)
    else:
      raise Exception(
          'Why are you trying to set_offered_to on a {} job?'.format(
              self.status()), self.pk)

  def notify_cant_reschedule_no_service_providers(self):
    subject = (
        'Unable to reschedule {}. No service providers available.'.format(
            self._meta.model_name))
    message = (
        '{}\n\nYou could either permanently cancel the job or find '
        'more service providers.').format(self.keys_url())
    notify(self.alerts_email(), subject, message)

  def set_accepted_by(self, worker, **kwargs):
    self.accepted_by = worker
    self.save()

  def get_service_provider_data(self):
    service_providers = []
    shouldnt_offer_to = self.get_canceled_or_declined_workers()
    offered_to = self.offered_to.all()
    if set(shouldnt_offer_to) & set(offered_to) and (
        not self.get_child_class_instance().uses_work_co()):
      log_error(
          'Job offered to somebody who canceled or declined it.',
          '{} {}'.format(self.get_readable_work_title(), self.pk))
    for worker in offered_to:
      # lower() because Properly seems to store email addresses lower case, it
      # searches for them case sensitive, and for some reason the emails are
      # getting entered in our system with the first letter capitalized.
      service_providers.append({'email': worker.email.lower()})
    return list(sorted(service_providers, key=lambda x: x['email']))

  def get_canceled_or_declined_workers(self):
    return [cod.worker for cod in self.canceledordeclined_set.all()]

  def is_complete(self):
    return bool(self.completed_at)

  def overlapping_offers(self):
    return self._overlapping('OFFERED')

  def overlapping_accepted(self):
    return self._overlapping('ACCEPTED')

  def _overlapping(self, accepted_or_offered):
    # We don't check for overlap with flexible jobs.
    if self.fixed_or_flexible == FLEXIBLE or not self.accepted_by:
      return []
    # The whole point of work cos is to worry about
    # schedule problems so we don't have to.
    if self.get_child_class_instance().uses_work_co():
      return []
    jobs = Work.objects.concurrent(
        self.offered_start_time, self.get_expected_duration(),
        [self.accepted_by], accepted_or_offered)
    to_return = []
    for job in jobs:
      if job.pk != self.pk and not (
          job.get_child_class_instance().uses_work_co()):
        to_return.append(job)
    return to_return

  def remove_offered_to(self, worker):
    if self.only_offered_to(worker):
      raise Exception('You cant remove the final worker from a job!')
    self.offered_to.remove(worker)
    # Just in case somebody else in the offered_to list declined the job in the
    # meantime
    self.offered_to.set(
        remove_canceled_or_declined(self, self.offered_to.all()))

  def only_offered_to(self, worker):
    return [worker] == list(self.offered_to.all())

  def was_canceled(
      self, permanently_canceled_reason, api=None, nnow=None,
      message_sender=None, **kwargs):
    """ This is, like, oh we got canceled? It gets called after every cancel
    regardless of whether the cancel came from keys or from Properly.

    kwargs is there so Maintenance can override was_canceled so it can unblock
    rentals. """
    api = api or API()
    work = self.get_child_class_instance()
    if not work.canceled_at:
      # When we cancel it, we set the canceled_at property and then call the
      # API to cancel. So if canceled_at hasn't been set, we didn't cancel it.
      # In this case the desired behavior is to immediately reschedule.
      work.canceled_at = now()
      work.permanently_canceled_reason = permanently_canceled_reason
      work.save()
      if not permanently_canceled_reason:
        work.reschedule(api, nnow=nnow, message_sender=message_sender)

  def was_canceled_by_worker(self, api=None, nnow=None, message_sender=None):
    if self.accepted_by:
      # You can't count on accepted_by being there because Properly often
      # fails to send webhooks, including jobRequest.accepted
      CanceledOrDeclined.objects.get_or_create(
          worker=self.accepted_by, work=self)
    self.was_canceled(
        permanently_canceled_reason='', api=api, nnow=nnow,
        message_sender=message_sender)

  def was_declined(self, worker, **kwargs):
    if worker:
      CanceledOrDeclined.objects.get_or_create(worker=worker, work=self)

  def impermanent_cancel(self, api=None):
    self.cancel('', api=api)

  def cancel(self, permanently_canceled_reason, api=None, **kwargs):
    """ This is, like, push out a cancel you guys. This made sense when we used
    Properly but now was_canceled and cancel should be combined. """
    self.was_canceled(permanently_canceled_reason, **kwargs)

  def canceled(self):
    return bool(self.canceled_at)

  def can_calculate_duration(self):
    return not self.explain_why_cant_calculate_duration()

  def explain_why_cant_calculate_duration(self):
    if not self.started_at:
      return (
          'This job is missing a start time. Perhaps Properly failed to '
          'inform us? You\'ll have to look up the duration and enter it '
          'manually.')
    if not self.completed_at:
      return 'This job doesn\'t appear to be done yet.'

  def get_actual_duration(self):
    if not self.started_at:
      raise Exception(
          'I cant calculate duration because this job doesnt have a '
          'started_at. Check can_calculate_duration before calling '
          'get_actual_duration.')
    if not self.completed_at:
      raise Exception(
          'I cant calculate duration because this job hasnt been completed.')
    return self.completed_at - self.started_at

  def get_paid_duration(self):
    min_hour = timedelta(hours=self.accepted_by.hour_min)
    return max(min_hour, self.get_actual_duration())

  def get_readable_duration(self):
    return get_readable_duration(self.get_paid_duration())

  def get_cost(self):
    return self.accepted_by.hour_rate * self.get_paid_duration().hours

  def late_start(self):
    if not self.started_at:
      raise Exception(
          'This job wasnt started yet so I cant say how late it was started.')
    if self.started_at <= self.offered_start_time:
      return timedelta()
    return self.started_at - self.offered_start_time

  def can_edit(self):
    if self.in_properly():
      return not self.job_request_id
    return not self.started_at

  def in_properly(self):
    return True

  def created_in_properly(self):
    return bool(self.job_request_id)

  def created_already(self):
    # Some tests may just set job_request_id, and when we skip Properly (when
    # it comes to maintenance), some real jobs will only have
    # creation_confirmed.
    return bool(self.creation_confirmed) or self.created_in_properly()

  def reopen(self):
    """ Take this canceled job and clear out the canceled stuff so it can be
    recreated. For instance, you impermanently cancel a cleaning because an
    independent cleaner had it but you want the new cleaning company to get it.
    """
    if not self.canceled_at:
      log_error('Trying to reopen a non-canceled job?', str(self.pk))
    self.canceled_at = None
    self.accepted_by = None
    self.job_request_id = ''
    self.creation_confirmed = None
    self.creation_started = None
    self.creation_error = ''
    self.action_on_properly = False
    self.action_on_keys = False
    self.permanently_canceled_reason = ''
    self.action_on_keys_canceled_on_properly_at = None

  class Meta:
    ordering = ('-offered_start_time',)


class CanceledOrDeclined(models.Model):
  """ Don't offer jobs to service workers if they've declined or canceled the
  job already. Apparently that's a big source of frustration and noise at the
  moment. """
  worker = models.ForeignKey(Worker, on_delete=models.CASCADE)
  work = models.ForeignKey(Work, on_delete=models.CASCADE)
