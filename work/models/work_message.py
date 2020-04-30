"""
Messages that apply to all types of work.
"""
from datetime import timedelta
import time

from django.conf import settings
from django.dispatch import receiver

from commands.models import background_command
from work.models.fixed_or_flexible import FIXED, FLEXIBLE
from work.models.message import (
    Message, MessageSender, SubjectLine, ONE_WORKER_1_TIME_SLOT_2_JOBS,
    SMS, EMAIL, GOOD_MORNING_TODAYS_JOBS, GOOD_MORNING_2ND_SMS,
    START_10_MINUTES_LATE, START_15_MINUTES_LATE, START_20_MINUTES_LATE,
    SKEPTICAL_CAN_FINISH_FLEXIBLE_ON_TIME,
    NOT_STARTED_1_HOUR_AFTER_SHOULD_BE_DONE, JOB_ON_PROPERLY_AND_KEYS)
from work.models.work import Work
from util.signals import post_sync
from util.timezone import now, dt_to_time_str


@background_command
def send_9am_daily_job_reminders_background():
  send_9am_daily_job_reminders()


@background_command
def send_through_the_day_work_messages_background():
  """ I used to be more thoughtful about these, lovingly scheduling each one.
  But then there were kind of a lot of messages and then we were in a bunch of
  timezones and it started to get unruly. So now I just run these
  (and cleaning messages) every 5 minutes basically from 10am new york time to
  6pm arizona time. """
  send_delayed_work_start_messages()
  send_cant_complete_flexible_in_time()
  send_not_started_an_hour_after_supposed_to_be_done()
  resend_server_error_messages()


@receiver(post_sync)
def post_sync_work(sender, instance, *args, **kwargs):
  if isinstance(instance, Work) and (
      settings.PROD or 'message_sender' in kwargs):
    message_sender = kwargs.get('message_sender', MessageSender())

    overlapping = list(instance.overlapping_accepted())
    if overlapping:
      alert_overlap_accepted([instance] + overlapping, message_sender)

    if instance.action_on_keys and instance.action_on_properly:
      alert_action_on_keys_and_properly(instance, message_sender)


def alert_action_on_keys_and_properly(work, message_sender):
  if not Message.objects.filter(
      reason=JOB_ON_PROPERLY_AND_KEYS, work=work).exists():
    Message.objects.create_and_send_email(
        settings.EMAIL_ERRORS_TO, JOB_ON_PROPERLY_AND_KEYS, work.keys_url(),
        work, message_sender=message_sender)


def alert_overlap_accepted(overlapping, message_sender):
  """ 1 worker, 1 time slot, >1 fixed jobs. overlapping is a list. """
  pks = [work.pk for work in overlapping]
  workers = set([overlap.accepted_by for overlap in overlapping])
  worker = list(workers)[0]
  alert_emails = set()
  job_addresses = []
  for overlap in overlapping:
    rental = overlap.get_rental()
    alert_emails.add(rental.building.alerts_email)
    job_addresses.append(rental.full_address)
  job_addresses.sort()

  if len(workers) != 1:
    raise Exception(str(pks))

  subject = SubjectLine.objects.get_subject_line(
      ONE_WORKER_1_TIME_SLOT_2_JOBS)

  content = (
      'A worker has accepted two or more jobs for the same time slot.\n\n'
      'Worker: {} {} {}\n'
      'Time: {}\n'
      '{}').format(
          worker.name, worker.email, worker.phone,
          overlapping[0].get_full_start_time_str(),
          '\n'.join(job_addresses))

  existing = Message.objects.existing_content_today(
      ONE_WORKER_1_TIME_SLOT_2_JOBS)
  if content not in existing:
    message_sender.send(Message.objects.create(
        to=','.join(sorted(alert_emails)),
        reason=ONE_WORKER_1_TIME_SLOT_2_JOBS, kind=EMAIL, subject=subject,
        content=content, work=overlapping[0], when=now()))


def send_9am_daily_job_reminders(message_sender=None, nnow=None):
  message_sender = message_sender or MessageSender()
  worker_lookup = {}  # {worker: [cleaning, one_off]}
  for work in Work.objects.todays_jobs(nnow=nnow):
    for worker in work.send_good_morning_todays_jobs_to():
      if worker not in worker_lookup:
        worker_lookup[worker] = []
      worker_lookup[worker].append(work)
  for worker, jobs in worker_lookup.items():
    sorted_jobs = sorted(jobs, key=lambda x: x.pk)
    if not Message.objects.filter(
        reason=GOOD_MORNING_TODAYS_JOBS, work=sorted_jobs[0]).exists():
      work_summaries = []
      for work in sorted_jobs:
        work_summaries.append('{} {}'.format(
            work.get_title(), work.get_address_and_time()))
      subject = SubjectLine.objects.get_subject_line(GOOD_MORNING_TODAYS_JOBS)
      content = (
          '{}\n{}').format(
              subject, '\n'.join(work_summaries))
      message_sender.send(Message.objects.create(
          to=worker.phone, reason=GOOD_MORNING_TODAYS_JOBS, kind=SMS,
          content=content, work=sorted_jobs[0], when=now()))

      # Sometimes the second good morning SMS arrived first. Try to hack around
      # that.
      if settings.PROD:
        time.sleep(5)

      second_subject = SubjectLine.objects.get_subject_line(
          GOOD_MORNING_2ND_SMS)
      customized = second_subject and GOOD_MORNING_2ND_SMS != second_subject
      if customized:
        Message.objects.create_and_send_sms(
            to=worker.phone, reason=GOOD_MORNING_2ND_SMS,
            content=second_subject, work=sorted_jobs[0],
            message_sender=message_sender)


def resend_server_error_messages(message_sender=None, nnow=None):
  nnow = nnow or now()
  message_sender = message_sender or MessageSender()
  for message in Message.objects.filter(
      when__gte=nnow - timedelta(days=1),
      please_resend_due_to_server_error=True):
    message_sender.send(message)


def send_not_started_an_hour_after_supposed_to_be_done(
    nnow=None, message_sender=None):
  nnow = nnow or now()
  message_sender = message_sender or MessageSender()

  for work in Work.objects.todays_jobs(nnow=nnow):
    sent_already = Message.objects.filter(
        reason=NOT_STARTED_1_HOUR_AFTER_SHOULD_BE_DONE, work=work)
    if work.started_at or nnow <= work.get_expected_done_by() or (
        sent_already.exists()):
      continue
    message_sender.send(Message.objects.create(
        to=work.alerts_email(),
        reason=NOT_STARTED_1_HOUR_AFTER_SHOULD_BE_DONE, kind=EMAIL,
        subject=NOT_STARTED_1_HOUR_AFTER_SHOULD_BE_DONE,
        content=_job_details_for_alert(work), work=work, when=nnow))


def send_cant_complete_flexible_in_time(nnow=None, message_sender=None):
  """ Bob accepted a 2 hour flexible job that should be done by 7pm, but it's
  5:15pm and he hasn't started yet. Now I'm skeptical he'll be done in
  time. """
  nnow = nnow or now()
  message_sender = message_sender or MessageSender()

  for work in Work.objects.todays_jobs(nnow=nnow):
    sent_already = Message.objects.filter(
        reason=SKEPTICAL_CAN_FINISH_FLEXIBLE_ON_TIME, work=work)
    if work.fixed_or_flexible == FIXED or work.started_at or (
        sent_already.exists()):
      continue
    time_until_deadline = work.get_deadline() - nnow
    time_until_grace_period = time_until_deadline + timedelta(minutes=15)
    # Sigh, Decimals. Can't really use them anywhere I guess.
    duration = timedelta(hours=float(work.get_expected_duration()))
    if duration >= time_until_grace_period:
      content = (
          'This flexibly scheduled job is due at {}, but it hasn\'t '
          'been started, it\'ll take about {} hours to complete, and now '
          'it\'s {}.\n\n{}').format(
              dt_to_time_str(work.get_deadline()),
              work.get_expected_duration(), dt_to_time_str(nnow),
              _job_details_for_alert(work))
      message_sender.send(Message.objects.create(
          to=work.alerts_email(),
          reason=SKEPTICAL_CAN_FINISH_FLEXIBLE_ON_TIME, kind=EMAIL,
          subject=SKEPTICAL_CAN_FINISH_FLEXIBLE_ON_TIME, content=content,
          work=work, when=nnow))


def send_delayed_work_start_messages(nnow=None, message_sender=None):
  nnow = nnow or now()
  message_sender = message_sender or MessageSender()

  for work in Work.objects.todays_jobs(nnow=nnow):
    should_start_at = work.get_start_time()
    if nnow < should_start_at:
      continue
    if work.fixed_or_flexible == FLEXIBLE:
      # Flexibly scheduled jobs don't have to start at a particular time, they
      # just have to be done by a particular time.
      return
    if work.started_at:
      # These messages are all, like, "The cleaning has not been started..."
      # and they are meant to help us make work happen that hasn't already. I
      # don't believe there's a need to send these messages if the work did
      # start.
      continue
    # accepted_at was added later on so I'm not assuming it exists.
    if work.accepted_at and (
        work.accepted_at >= work.offered_start_time):
      # Clearly some last minute confusion is going on. Best to let this get
      # handled manually.
      continue
    # Cleanings NEED to happen and should always alert if they start late, even
    # if nobody accepted the job. Unaccepted maintenance on the other hand
    # isn't necessarily a big deal.
    if not work.accepted_by and not work.alert_unaccepted_late_start():
      continue

    elapsed = (nnow - should_start_at).seconds
    ten = 10 * 60
    fifteen = 15 * 60
    twenty = 20 * 60
    if _elapsed_yet_not_tardy(elapsed, ten):
      if not Message.objects.filter(
          reason=START_10_MINUTES_LATE, work=work).exists():
        if work.uses_work_co():
          _send_work_co_10_min_late(work, nnow, message_sender)
        else:
          _send_independent_worker_10_min_late(work, nnow, message_sender)
        continue
    if _elapsed_yet_not_tardy(elapsed, fifteen) and (
        work.uses_independent_workers()):
      if not Message.objects.filter(
          reason=START_15_MINUTES_LATE, work=work).exists():
        _send_independent_worker_15_min_late(work, nnow, message_sender)
        continue
    if _elapsed_yet_not_tardy(elapsed, twenty) and work.uses_work_co():
      if not Message.objects.filter(
          reason=START_20_MINUTES_LATE, work=work).exists():
        _send_work_co_20_min_late(work, nnow, message_sender)
        continue


def _elapsed_yet_not_tardy(elapsed, cutoff):
  """ Has enough time elapsed to send the message, yet it's not TOO late to
  send the message? This message could be tardy because todays_jobs pulls back
  only accepted jobs. Let's say the cleaning was supposed to start at 11:15 but
  didn't get accepted until 11:45. Don't send out a START_10_MINUTES_LATE at
  11:46 or whatever. """
  return cutoff < elapsed and elapsed < cutoff + 10 * 60


def _send_work_co_10_min_late(work, nnow, message_sender):
  work_co = work.get_work_co()
  subject = SubjectLine.objects.get_subject_line(START_10_MINUTES_LATE)
  who = work.accepted_by or work.offered_to.first()
  sentence_1 = 'This job was supposed to start'
  if who:
    sentence_1 = '{} was supposed to start the work'.format(who.name)
  content = 'Hello! {} at {} 10 minutes ago.'.format(
      sentence_1, work.get_rental().nickname)
  message_sender.send(Message.objects.create(
      to=work_co.alerts_email, reply_to=work.alerts_email(),
      reason=START_10_MINUTES_LATE, kind=EMAIL,
      subject=subject, content=content, work=work, when=nnow))


def _send_independent_worker_10_min_late(work, nnow, message_sender):
  worker = work.accepted_by
  if worker:
    content = (
        'Hi {}. We saw that you haven’t started the job yet. '
        'If you are at the building, please start the job. '
        'If you are running behind, please let us know your '
        'ETA.').format(worker.name)
    message_sender.send(Message.objects.create(
        to=worker.phone, reason=START_10_MINUTES_LATE, kind=SMS,
        subject='', content=content, work=work, when=nnow))


def _send_independent_worker_15_min_late(work, nnow, message_sender):
  worker = work.accepted_by
  worker_stuff = 'No independent worker accepted this job.'
  if worker:
    worker_stuff = (
        'We already sent the worker an SMS reminder to start the job '
        'or give us their ETA if they are running behind.\n\n'
        'Worker name: {}\n'
        'Worker phone number: {}\n\n'
        'Next steps:\n'
        '1. Check Front and see if the worker has replied to the SMS\n'
        '2. If they have not replied, call the worker and ask when '
        'they will be starting the work\n'
        '3. If you are not able to get in touch by 11:50 am, cancel the '
        'Properly job and check to make sure our system sent out a new '
        'job. You may also need to start calling workers to see who '
        'is available.').format(worker.name, worker.phone)
  subject = SubjectLine.objects.get_subject_line(START_15_MINUTES_LATE)
  content = (
      '{}\n\n{} has not been started at {}. {}').format(
          work.keys_url(), work.get_readable_work_title(),
          work.get_address_and_time(), worker_stuff)
  to = work.alerts_email()
  message_sender.send(Message.objects.create(
      to=to, reason=START_15_MINUTES_LATE, kind=EMAIL, subject=subject,
      content=content, work=work, when=nnow))


def _send_work_co_20_min_late(work, nnow, message_sender):
  subject = SubjectLine.objects.get_subject_line(START_20_MINUTES_LATE)
  to = work.alerts_email()
  content = (
      '{}\n\nThe work at {} was supposed to start 20 minutes ago. We '
      'sent the work company an email 10 minutes ago.\n\n'
      'Work company alerts email: {}\n').format(
          work.keys_url(), work.get_address_and_time(), to)
  message_sender.send(Message.objects.create(
      to=to, reason=START_20_MINUTES_LATE, kind=EMAIL, subject=subject,
      content=content, work=work, when=nnow))


def _job_details_for_alert(work):
  worker_str = ''
  if work.accepted_by:
    worker_str = '\nService provider: {} {} {}'.format(
        work.accepted_by.name,
        work.accepted_by.email,
        work.accepted_by.phone)
  return '{}\nTitle: {}\nRental: {}{}'.format(
      work.keys_url(), work.get_readable_work_title(),
      work.get_rental().full_address, worker_str)
