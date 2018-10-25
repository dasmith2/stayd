from datetime import date

from django.db import models
from django.utils.timezone import now

from errors.models import log_error
from properly.models.cleaning import Cleaning
from properly.models.message_sender import MessageSender, EMAIL, SMS
from util.background import background
from util.timezone import utc_dt_to_tz_dt


UNCLAIMED_CLEANING_IN_LT_48_HOURS = (  # Email
    'Unclaimed cleaning in less than 48 hours')
ONE_CLEANER_1_TIME_SLOT_2_JOBS = '1 cleaner, 1 time slot, 2 jobs'  # Email
GOOD_MORNING_TODAYS_JOBS = 'Good morning! Today\'s cleanings:'  # SMS
START_10_MINUTES_LATE = (  # SMS
    'This cleaning was supposed to start 10 minutes ago')
START_15_MINUTES_LATE = (  # Ema
    'Their cleaning was supposed to start 15 minutes ago')
CLEANING_30_MINUTES_TOO_LONG = 'This cleaning took half an hour too long'  # Em

MESSAGE_REASONS = [
    UNCLAIMED_CLEANING_IN_LT_48_HOURS, ONE_CLEANER_1_TIME_SLOT_2_JOBS,
    GOOD_MORNING_TODAYS_JOBS, START_10_MINUTES_LATE, START_15_MINUTES_LATE,
    CLEANING_30_MINUTES_TOO_LONG]


REASON_CHOICES = [(reason, reason) for reason in MESSAGE_REASONS]


@background
def send_9am_daily_job_reminders_background(message_sender=MessageSender()):
  cleaning_lookup = {}  # {cleaner: [cleaning, cleaning]}
  for cleaning in Cleaning.objects.todays_cleanings():
    if cleaning.accepted_by not in cleaning_lookup:
      cleaning_lookup[cleaning.accepted_by] = []
    cleaning_lookup[cleaning.accepted_by].append(cleaning)
  existing = Message.objects.existing_content_today(GOOD_MORNING_TODAYS_JOBS)
  for cleaner, cleanings in cleaning_lookup.items():
    cleaning_summaries = []
    for cleaning in cleanings:
      cleaning_summaries.append(cleaning.get_address_and_time())
    greeting = SubjectLine.objects.get_subject_line(GOOD_MORNING_TODAYS_JOBS)
    content = '{} {}'.format(greeting, ', '.join(cleaning_summaries))
    if content not in existing:
      message_sender.send(Message.objects.create(
          to=cleaner.phone, reason=GOOD_MORNING_TODAYS_JOBS, kind=SMS,
          content=content))


@background
def send_10_minute_late_cleaning_notifications_background(
    nnow=None, message_sender=MessageSender()):
  """ These go out to the cleaners. """
  nnow = nnow or now()
  existing = Message.objects.existing_content_today(START_10_MINUTES_LATE)
  for cleaning in Cleaning.objects.todays_cleanings():
    elapsed = (nnow - cleaning.get_start_time()).seconds
    if elapsed > 10 * 60:
      greeting = SubjectLine.objects.get_subject_line(START_10_MINUTES_LATE)
      content = '{} {}'.format(greeting, cleaning.get_address_and_time())
      if content not in existing:
        message_sender.send(Message.objects.create(
            to=cleaner.phone, reason=START_10_MINUTES_LATE, kind=SMS,
            content=content))
        if elapsed > 15 * 60:
          log_error(
              'START_10_MINUTES_LATE message went out late (ironically)',
              (cleaning.pk, nnow, cleaning.get_start_time(), elapsed))


def send_15_minute_late_cleaning_notifications(message_sender=MessageSender()):
  """ These go out to the building email addresses. """


class SubjectLineManager(models.Manager):
  def get_subject_line(self, reason):
    subject_line = self.filter(reason=reason).first()
    if not subject_line:
      subject_line = self.create(reason=reason, subject=reason)
    return subject_line.subject


class SubjectLine(models.Model):
  reason = models.CharField(
      choices=REASON_CHOICES, max_length=100, unique=True)
  subject = models.TextField(help_text=(
      'For emails, these become the subject line. For SMSs, they\'re '
      'prepended to the message.'))


KIND_SEND_MESSAGE_CHOICES = (
    (EMAIL, EMAIL),
    (SMS, SMS))


class MessageManager(models.Manager):
  def existing_content_today(self, reason):
    return set([message.content for message in Message.objects.filter(
        when__date=date.today(), reason=reason)])


class Message(models.Model):
  when = models.DateTimeField(auto_now_add=True, db_index=True)
  to = models.CharField(max_length=200)
  reason = models.CharField(
      choices=REASON_CHOICES, max_length=100)
  kind = models.CharField(choices=KIND_SEND_MESSAGE_CHOICES, max_length=20)
  subject = models.TextField(blank=True, null=True, help_text=(
      'This only applies to emails.'))
  content = models.TextField()
  delivery_error = models.TextField(null=True, blank=True)

  objects = MessageManager()

  def send(self, message_sender=MessageSender()):
    if self.when:
      raise Exception('This message was sent already.')
    self.when = now()
    message_sender.send(self)
    self.save()
