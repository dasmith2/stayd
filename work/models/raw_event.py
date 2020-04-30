""" This file is all about what happens when we receive webhooks from
properly. """
from datetime import timedelta
import json
import re

from django.db import models, IntegrityError
from django.shortcuts import reverse
from django.utils.dateparse import parse_datetime
from util.timezone import now

from commands.models import background_command
from errors.models import log_error
from work.api import API, SERVER_ERROR
from work.models.message import MessageSender, Message, NOBODY_LEFT_TO_DO_A_JOB
from work.models.rental import ProperlyRental
# from work.models.sync_jobs import do_sync_jobs
from work.models.ticket import Ticket
from work.models.work import Worker, Work
from util.rm_old import RmOldManager
from util.signals import post_sync
from util.urls import keys_url
from util.webhook import Webhook


@background_command
def retry_properly_webhooks_background():
  for raw in RawEvent.objects.filter(handled_at__isnull=True):
    raw.handle()


def find_job_request_id(job_request_id, since=None):
  """ Go through the webhooks since `since` and return those whose jobRequestId
  matches the given job_request_id """

  def matcher(data):
    return data.get('input', {}).get('jobRequestId', None) == job_request_id
  return list(_find(since, matcher))


def find_error(error, since=None):
  """ Go through the webhooks since `since` and return those with the given
  error. """

  def matcher(data):
    results = data.get('results', [])
    if len(results):
      return results[0].get('error', None) == error
  return list(_find(since, matcher))


def _find(since, matcher):
  since = since or now() - timedelta(days=7)
  for raw in RawEvent.objects.filter(created_at__gte=since):
    data = json.loads(raw.json)
    if matcher(data):
      yield raw


def server_error_creation(since=None):
  """ Print a helpful summary of all the work that got a SERVER_ERROR on
  creation. Guess what scenario this was useful under. """
  works = set()
  for raw in find_error(SERVER_ERROR, since):
    work = raw.work.get_child_class_instance()
    works.add(work)
  to_return = []
  for work in works:
    to_return.append('{} {} {} {} {}'.format(
        work.offered_start_time.date(), work.__class__.__name__, work.pk,
        work.get_readable_work_title(), work.get_rental().nickname))
  return '\n'.join(to_return)


class RawEvent(Webhook):
  event_name = models.CharField(
      max_length=100, null=True, blank=True, help_text=(
          'This doesnt get set until the event is handled.'))
  work = models.ForeignKey(
      Work, null=True, blank=True, on_delete=models.CASCADE)
  worker = models.ForeignKey(
      Worker, null=True, blank=True, on_delete=models.CASCADE)
  error = models.TextField(null=True, blank=True, help_text=(
      'The error in this webhook, if any.'))

  objects = RmOldManager()

  def __repr__(self):
    return '<RawEvent {}: {} {}>'.format(
        self.pk, self.created_at.date(), self.event_name)

  class Meta:
    ordering = ('-created_at',)

  def url(self):
    return reverse('raw_event_detail', kwargs={'pk': self.pk})

  def keys_url(self):
    return keys_url(self.url())

  def handle(
      self, api=API(), message_sender=MessageSender(), scheduling_api=None,
      nnow=None):
    nnow = nnow or now()
    data = json.loads(self.json)

    event_name = data.get('eventName', None)
    if not event_name:
      message = (
          'If this webhook is nonsense as I suspect, do nothing. '
          'Its for raw event {}:\n\n{}').format(
              self.pk, json.dumps(data, indent=2))
      log_error('Can you just double check this properly webhook?', message)
      self.handled_at = nnow
      self.save()
      return

    work = None
    work_related = event_name.find('jobRequest') >= 0
    if work_related:
      work = self._get_work(data)

    self.event_name = event_name
    self.save()

    result_0 = data.get('results', [None])[0]

    # You see this in accepted and declined by service provider
    worker_email = result_0 and result_0.get('serviceProvider', None)

    if result_0:
      ignore_events = [
          'booking.canceled', 'booking.changed', 'property.update',
          'checklist.create', 'checklist.disable']
      if 'error' in result_0:
        # We can't know if a cancelation actually took or not at this point. So
        # don't alert now, but let sync_jobs alert if it discovers there's a
        # job we thought we canceled but actually isn't.
        if event_name != 'jobRequest.canceled':
          self._handle_error(result_0, data, api, message_sender, nnow)
      elif event_name in ignore_events:
        pass
      elif event_name == 'listing.cleaningJobs':
        # do_sync_jobs(data['results'], message_sender, api=api, nnow=nnow)
        pass
      elif event_name == 'booking.create':
        # No Bookings any more.
        pass
      elif work_related:
        if work:
          self.work = work
          self.save()
          work = work.get_child_class_instance()
          created_at = parse_datetime(data['createdAt'])
          work_changed = True
          if event_name == 'jobRequest.create':
            work.creation_confirmed = nnow
            work.save()
          if event_name == 'jobRequest.accepted':
            if not self.handle_accepted_job_request(
                work, worker_email, message_sender, api, scheduling_api):
              return
            work.accepted_at = created_at
            work.action_on_properly = True
            work.save()
          elif event_name.find('canceled') >= 0:
            # Yep, one time I saw a canceled event for a job that was completed
            # already. If we're doing this one on keys, we expect it to be
            # canceled on Properly, but the job isn't actually canceled.
            if not work.completed_at and not work.action_on_keys:
              if event_name == 'jobRequest.canceled':
                work.was_canceled(
                    permanently_canceled_reason='', api=api, nnow=nnow,
                    message_sender=message_sender)
              elif event_name == 'jobRequest.canceledByServiceProvider':
                self.worker = work.accepted_by
                self.save()
                work.was_canceled_by_worker(
                    api=api, nnow=nnow, message_sender=message_sender)
              else:
                log_error(
                    'A new way to cancel properly jobs?', self.keys_url())
          elif event_name == 'jobRequest.started':
            # Sometimes properly will send us multiple started webhooks for the
            # same job!
            work.action_on_properly = True
            if not work.started_at:
              work.started_at = created_at
            work.save()
          elif event_name == 'jobRequest.completed':
            # I don't think properly ever sent us multiple completed webhooks
            # for the same job, but you can understand my paranoia.
            work.action_on_properly = True
            if not work.completed_at:
              work.completed_at = created_at
              work.all_tasks_complete = self._check_for_complete_checklists(
                  data)
            work.save()
          elif event_name == 'jobRequest.taskUpdated':
            self._check_for_complete_checklists(data)
          elif event_name == 'jobRequest.declinedByServiceProvider':
            work_changed = False
            work.was_declined(
                self.get_worker(worker_email), message_sender=message_sender)
          elif event_name == 'jobRequest.problemReported':
            work_changed = False
            Ticket.objects.create_from_properly_reported_problem(self)
          else:
            # e.g. jobRequest.declinedByAllServiceProviders. Note that Properly
            # sends a declinedByServiceProvider in addition to declinedByAll
            work_changed = False
          if work_changed:
            post_sync.send(
                sender=type(work), instance=work,
                message_sender=message_sender)
      else:
        log_error(
            'Not sure how to handle {} webhook'.format(event_name),
            'RawEvent {}. json {}'.format(self.pk, data))
        return
    self.handled_at = nnow
    try:
      self.save()
    except IntegrityError as ex:
      # One time I got one of these and for the life of me I couldn't figure
      # out which webhook it came from. (one day later) OK the latest error is
      # for a webhook that doesn't actually exist. I still have no idea what's
      # happening. Adding yet more info to the error message.
      message = 'RawEvent {} {} caused {}.\n\n{}'.format(
          self.pk, event_name, ex, json.dumps(json.loads(self.json), indent=2))
      log_error('Integrity error handling properly webhook', message)

  def _handle_error(self, result_0, data, api, message_sender, nnow):
    error = result_0['error']
    self.error = error
    self.save()
    redo_id = re.compile(
        r'Could not find a property for sourcePropertyId: (.+)')
    yep_redo = redo_id.match(error)
    accepted_already = (
        'You can only modify serviceProviders before the job request is '
        'accepted.')
    started_already = (
        'You can only modify the job request before it starts.')
    event_name = data.get('eventName', None)
    if event_name == 'jobRequest.update' and error in (
        accepted_already, started_already):
      # As an example, see this cleaning:
      # https://keys.hihoward.com/admin/work/cleaning/157/change/ It
      # was accepted at almost exactly the same time a different Work was
      # accepted which caused a race with removing service providers from
      # accepted jobs.
      return  # Yes it was handled.
    if event_name == 'booking.create':
      # No bookings any more
      pass
    elif event_name == 'jobRequest.create':
      client_request_id = data.get('clientRequestId', None)
      if client_request_id:
        work = Work.objects.filter(
            create_properly_job_client_request_id=client_request_id).first()
        if work:
          work = work.get_child_class_instance()
          self.work = work
          self.handled_at = now()
          self.save()

          if error == SERVER_ERROR:
            if work.handle_server_error_in_create_webhook(message_sender):
              return  # Yes it was handled.

          # Yes, one time I received 2 webhooks in quick succession. The first
          # one was a successful creation webhook, the second had a weird one
          # about duplicate ids in Properly's system.
          if not work.creation_confirmed:
            work.creation_error = error
            work.save()
    if yep_redo:
      rc = ProperlyRental.objects.get(
          source_property_id=yep_redo.groups()[0])
      rc.set_source_property_id(api)
      if data['eventName'] == 'booking.create':
        # We no longer do Properly
        pass
      else:
        log_error(
            'Invalid sourcePropertyId, but not booking.create',
            'raw pk {}'.format(self.pk))
      return

    coudnt_find = (
        'Could not find service providers with the following emails')
    if error.find(coudnt_find) >= 0:
      # Referencing a job that's no longer on our system, so ignore it I guess.
      if not self.work:
        return
      # As of today, nobody cares if service providers aren't in Properly!
      return

    booking_already_exists = re.compile(
        r'Booking with sourceBookingId .+ already exists')
    booking_already_canceled = re.compile(
        r'you cannot cancel a cancelled booking')
    if (not booking_already_exists.search(error)) and (
        not booking_already_canceled.search(error)):
      subject = 'Error returned by Properly webhook'
      if error == SERVER_ERROR:
        subject = 'Unknowable server error returned by Properly webhook'
      log_error(
          subject,
          'RawEvent {}. Error {}\n\n{}'.format(
              self.pk, error, json.dumps(data, indent=2)),
          always_new_error=True)

  def _check_for_complete_checklists(self, data):
    """ The return value is set on the Work and is used by cleanings, where we
    evaluate cleaners based on whether or not they check everything for a
    cleaning. The calls to checklist_complete_on_properly are used by
    Maintenance to pass along word to tickets that specific checklists were
    accomplished. """
    all_done = True
    for result in data.get('results', []):
      for checklist in result.get('checklists', []):
        checklist_id = checklist['checklistId']
        checklist_done = True
        for task_group in checklist.get('taskGroups', []):
          for task in task_group.get('tasks', []):
            if not task['done']:
              all_done = False
              checklist_done = False
        if checklist_done and self.work:
          who_completed_it = result['serviceProvider']['name']
          self.work.get_child_class_instance().checklist_complete_on_properly(
              who_completed_it, checklist_id)
    return all_done

  def _get_work(self, data):
    first_spot = data.get('input', {}).get('jobRequestId', None)
    second_spot = data['results'][0].get('jobRequestId', None)
    job_request_id = first_spot or second_spot
    if job_request_id:
      work = Work.objects.filter(job_request_id=job_request_id).first()
      if work:
        self.work = work
        self.save()
      return work

  def handle_accepted_job_request(
      self, work, worker_email, message_sender, api, scheduling_api):
    # One time, a cleaning had an error on creation but nevertheless the job
    # was accepted. So evidentally it got created. The code assumes that if
    # there's a creation_error, it didn't get created. So clear this out.
    work.creation_error = ''

    worker = self.set_worker(worker_email)
    if self.worker:
      # Maintenance may need to block the night once work is accepted, hence
      # the scheduling api.
      work.set_accepted_by(worker, scheduling_api=scheduling_api)
      for other_offer in work.overlapping_offers():
        if other_offer.only_offered_to(worker):
          other_offer = other_offer.get_child_class_instance()
          content = (
              '{} accepted {}. So far so good. BUT! There\'s {} that was only '
              'offered to {}, so now there\'s nobody left to do that job, so '
              'I canceled it.').format(
                  worker.name, work, other_offer, worker.name)
          other_offer.cancel(content)
          Message.objects.create_and_send_email(
              to=other_offer.get_rental().building.alerts_email,
              reason=NOBODY_LEFT_TO_DO_A_JOB, content=content,
              work=other_offer, message_sender=message_sender)
        else:
          other_offer.remove_offered_to(worker)
      return True

  def get_worker(self, worker_email):
    if worker_email:
      return Worker.objects.filter(email__iexact=worker_email).first()

  def set_worker(self, worker_email):
    worker = self.get_worker(worker_email)
    if worker:
      self.worker = worker
      self.save()
      return worker

  def data(self):
    return json.loads(self.json)
