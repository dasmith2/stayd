from django.db import models
from django.dispatch import receiver
from django.utils.timezone import now

from errors.models import log_error
from properly.models.cleaning import Cleaning
from properly.models.message_sender import MessageSender, EMAIL, SMS
from util.signals import post_sync


UNCLAIMED_CLEANING_IN_LT_48_HOURS = (  # Email
    'Unclaimed cleaning in less than 48 hours')
ONE_CLEANER_1_TIME_SLOT_2_JOBS = '1 cleaner, 1 time slot, 2 jobs'  # Email
GOOD_MORNING_TODAYS_JOBS = 'Good morning! Today\'s cleanings:'  # SMS
START_10_MINUTES_LATE = (  # SMS
    'This cleaning was supposed to start 10 minutes ago:')
START_15_MINUTES_LATE = (  # Email
    'Their cleaning was supposed to start 15 minutes ago:')
CLEANING_TAKING_TOO_LONG = (  # Email
    'This cleaning is taking too long')

MESSAGE_REASONS = [
    UNCLAIMED_CLEANING_IN_LT_48_HOURS, ONE_CLEANER_1_TIME_SLOT_2_JOBS,
    GOOD_MORNING_TODAYS_JOBS, START_10_MINUTES_LATE, START_15_MINUTES_LATE,
    CLEANING_TAKING_TOO_LONG]


REASON_CHOICES = [(reason, reason) for reason in MESSAGE_REASONS]


@receiver(post_sync, sender=Cleaning)
def post_sync_cleaning(sender, instance, *args, **kwargs):
  message_sender = kwargs.get('message_sender', MessageSender())
  for overlapping in instance.overlapping():
    alert_overlap(instance, overlapping, message_sender)


def alert_overlap(first, overlapping, message_sender):
  cleaner = first.accepted_by
  alert_addresses = set([
      overlapping.reservation.rental.building.alerts_email,
      first.reservation.rental.building.alerts_email])
  for alert_email in alert_addresses:
    subject = SubjectLine.objects.get_subject_line(
        ONE_CLEANER_1_TIME_SLOT_2_JOBS)
    jobs = sorted([
        first.reservation.rental.full_address,
        overlapping.reservation.rental.full_address])
    content = (
        'cleaner: {} {} {}\n'
        'cleaning time: {}\n'
        'job 1: {}\n'
        'job 2: {}\n'
        'alerts sent to: {}').format(
            cleaner.name, cleaner.email, cleaner.phone,
            first.get_full_start_time_str(),
            jobs[0], jobs[1],
            ', '.join(alert_addresses))

    existing = Message.objects.existing_content_today(
        ONE_CLEANER_1_TIME_SLOT_2_JOBS)
    if content not in existing:
      message_sender.send(Message.objects.create(
          to=alert_email, reason=ONE_CLEANER_1_TIME_SLOT_2_JOBS, kind=EMAIL,
          subject=subject, content=content, cleaning=overlapping,
          when=now()))


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
  def send_9am_daily_job_reminders(self, message_sender=MessageSender()):
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
            content=content, cleaning=cleanings[0], when=now()))

  def send_10_minute_late_cleaning_notifications(
      self, nnow=None, message_sender=MessageSender()):
    """ These go out to the cleaners. """
    self._send_delayed_cleaning_start_messages(
        START_10_MINUTES_LATE, 10 * 60, 15 * 60, SMS, nnow=nnow,
        message_sender=message_sender)

  def send_15_minute_late_cleaning_notifications(
      self, nnow=None, message_sender=MessageSender()):
    """ These go out to the building email addresses. """
    self._send_delayed_cleaning_start_messages(
        START_15_MINUTES_LATE, 15 * 60, 20 * 60, EMAIL, nnow=nnow,
        message_sender=message_sender)

  def send_cleaning_taking_too_long_notifications(
      self, nnow=None, message_sender=MessageSender()):
    subject = SubjectLine.objects.get_subject_line(CLEANING_TAKING_TOO_LONG)
    for cleaning in Cleaning.objects.taking_too_long(nnow):
      if not Message.objects.filter(
          reason=CLEANING_TAKING_TOO_LONG, cleaning=cleaning).exists():
        cleaner = cleaning.accepted_by
        res = cleaning.reservation
        rental = res.rental
        content = (
            '{} {} {} {}\n'
            'Started at: {}\n'
            'Current duration: {}\n'
            'Completed yet: {}').format(
                cleaner.name, cleaner.phone, cleaner.email,
                rental.full_address,
                cleaning.get_readable_time_str(cleaning.started_at),
                cleaning.get_readable_duration(nnow), cleaning.is_complete())
        message_sender.send(Message.objects.create(
            to=rental.building.alerts_email, reason=CLEANING_TAKING_TOO_LONG,
            kind=EMAIL, subject=subject, content=content, cleaning=cleaning,
            when=nnow))

  def send_unclaimed_cleaning_in_lt_48_hours(
      self, nnow=None, message_sender=MessageSender()):
    for cleaning in Cleaning.objects.uh_oh_unclaimed(nnow=nnow):
      subject_line = SubjectLine.objects.get_subject_line(
          UNCLAIMED_CLEANING_IN_LT_48_HOURS)
      subject = '{} {}'.format(
          subject_line, cleaning.get_full_start_time_str())
      content = '{} {}'.format(
          cleaning.reservation.rental.full_address,
          cleaning.get_full_start_time_str())
      existing = Message.objects.existing_content_today(
          UNCLAIMED_CLEANING_IN_LT_48_HOURS, nnow=nnow)
      if content not in existing:
        message_sender.send(Message.objects.create(
            to=cleaning.reservation.rental.building.alerts_email,
            reason=UNCLAIMED_CLEANING_IN_LT_48_HOURS, kind=EMAIL,
            subject=subject, content=content, cleaning=cleaning,
            when=nnow))

  def existing_content_today(self, reason, nnow=None):
    nnow = nnow or now()
    return set([message.content for message in Message.objects.filter(
        when__date=nnow.date(), reason=reason)])

  def _send_delayed_cleaning_start_messages(
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
              to=to, reason=reason, kind=kind, subject=subject,
              content=content, cleaning=cleaning, when=nnow))
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
  cleaning = models.ForeignKey(Cleaning, on_delete=models.CASCADE)

  objects = MessageManager()

  def send(self, message_sender=MessageSender()):
    if self.when:
      raise Exception('This message was sent already.')
    self.when = now()
    message_sender.send(self)
    self.save()
