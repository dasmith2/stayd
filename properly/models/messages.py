from django.db import models
from django.utils.timezone import now

from properly.models.message_sender import MessageSender, EMAIL, SMS


UNCLAIMED_CLEANING_IN_LT_48_HOURS = 'Unclaimed cleaning in less than 48 hours'
ONE_CLEANER_1_TIME_SLOT_2_JOBS = '1 cleaner, 1 time slot, 2 jobs'
GOOD_MORNING_TODAYS_JOBS = 'Good morning! Today\'s jobs:'
START_10_MINUTES_LATE = 'Your job was supposed to start 10 minutes ago'
START_15_MINUTES_LATE = 'Their job was supposed to start 15 minutes ago'
CLEANING_30_MINUTES_TOO_LONG = 'This cleaning took half an hour too long'

MESSAGE_REASONS = [
    UNCLAIMED_CLEANING_IN_LT_48_HOURS, ONE_CLEANER_1_TIME_SLOT_2_JOBS,
    GOOD_MORNING_TODAYS_JOBS, START_10_MINUTES_LATE, START_15_MINUTES_LATE,
    CLEANING_30_MINUTES_TOO_LONG]


REASON_CHOICES = [(reason, reason) for reason in MESSAGE_REASONS]


@background
def send_9am_daily_job_reminders():
  pass


def send_10_minute_late_cleaning_notifications():
  """ These go out to the cleaners. """


def send_15_minute_late_cleaning_notifications():
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
  pass


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
