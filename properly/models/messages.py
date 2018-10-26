from django.db import models
from django.utils.timezone import now

from errors.models import log_error
from properly.models.cleaning import Cleaning
from properly.models.message_sender import MessageSender, EMAIL, SMS
from util.background import background


UNCLAIMED_CLEANING_IN_LT_48_HOURS = (  # Email
    'Unclaimed cleaning in less than 48 hours')
ONE_CLEANER_1_TIME_SLOT_2_JOBS = '1 cleaner, 1 time slot, 2 jobs'  # Email
GOOD_MORNING_TODAYS_JOBS = 'Good morning! Today\'s cleanings:'  # SMS
START_10_MINUTES_LATE = (  # SMS
    'This cleaning was supposed to start 10 minutes ago:')
START_15_MINUTES_LATE = (  # Email
    'Their cleaning was supposed to start 15 minutes ago:')
CLEANING_30_MINUTES_TOO_LONG = (  # Email
    'This cleaning took half an hour too long:')

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
    subject = SubjectLine.objects.get_subject_line(GOOD_MORNING_TODAYS_JOBS)
    content = '{} {}'.format(subject, ', '.join(cleaning_summaries))
    if content not in existing:
      message_sender.send(Message.objects.create(
          to=cleaner.phone, reason=GOOD_MORNING_TODAYS_JOBS, kind=SMS,
          content=content, when=now()))


@background
def send_10_minute_late_cleaning_notifications_background(
    nnow=None, message_sender=MessageSender()):
  """ These go out to the cleaners. """
  Message.objects.send_delayed_cleaning_start_messages(
      START_10_MINUTES_LATE, 10 * 60, 15 * 60, SMS, nnow=nnow,
      message_sender=message_sender)


@background
def send_15_minute_late_cleaning_notifications_background(
    nnow=None, message_sender=MessageSender()):
  """ These go out to the building email addresses. """
  Message.objects.send_delayed_cleaning_start_messages(
      START_15_MINUTES_LATE, 15 * 60, 20 * 60, EMAIL, nnow=nnow,
      message_sender=message_sender)


@background
def send_unclaimed_cleaning_in_lt_48_hours_background(
    nnow=None, message_sender=MessageSender()):
  for cleaning in Cleaning.objects.uh_oh_unclaimed(nnow=nnow):
    subject_line = SubjectLine.objects.get_subject_line(
        UNCLAIMED_CLEANING_IN_LT_48_HOURS)
    subject = '{} {}'.format(subject_line, cleaning.get_full_time_string())
    content = '{} {}'.format(
        cleaning.reservation.rental.full_address,
        cleaning.get_full_time_string())
    existing = Message.objects.existing_content_today(
        UNCLAIMED_CLEANING_IN_LT_48_HOURS, nnow=nnow)
    if content not in existing:
      message_sender.send(Message.objects.create(
          to=cleaning.reservation.rental.building.alerts_email,
          reason=UNCLAIMED_CLEANING_IN_LT_48_HOURS, kind=EMAIL,
          subject=subject, content=content,
          when=nnow))


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

  objects = SubjectLineManager()


KIND_SEND_MESSAGE_CHOICES = (
    (EMAIL, EMAIL),
    (SMS, SMS))


class MessageManager(models.Manager):
  def existing_content_today(self, reason, nnow=None):
    nnow = nnow or now()
    return set([message.content for message in Message.objects.filter(
        when__date=nnow.date(), reason=reason)])

  def send_delayed_cleaning_start_messages(
      self, reason, cutoff, error_cutoff, kind, nnow=None,
      message_sender=MessageSender()):
    nnow = nnow or now()
    existing = Message.objects.existing_content_today(reason, nnow=nnow)
    for cleaning in Cleaning.objects.todays_cleanings(nnow=nnow):
      start = cleaning.get_start_time()
      elapsed = (nnow - start).seconds
      if nnow > start and elapsed > cutoff:
        subject = SubjectLine.objects.get_subject_line(reason)
        to = None
        # OK, this is a little ugly. Emails go to building staff, SMSs go to
        # cleaners. Also subject lines don't make sense for SMSs.
        if kind == SMS:
          content = '{} {}'.format(subject, cleaning.get_address_and_time())
          subject = ''
          to = cleaning.accepted_by.phone
        elif kind == EMAIL:
          cleaner = cleaning.accepted_by
          content = '{} {} {} {}'.format(
              cleaner.name, cleaner.phone, cleaner.email,
              cleaning.get_address_and_time())
          subject += ' {}'.format(nnow.date())
          to = cleaning.reservation.rental.building.alerts_email
        else:
          raise Exception(kind)
        if content not in existing:
          message_sender.send(Message.objects.create(
              to=to, reason=reason, kind=kind,
              subject=subject, content=content, when=nnow))
          if elapsed > error_cutoff:
            log_error(
                '"{}" message went out late (ironically)', (
                    reason, cleaning.pk, nnow, cleaning.get_start_time(),
                    elapsed))


class Message(models.Model):
  when = models.DateTimeField(db_index=True)
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
