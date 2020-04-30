"""
This file contains the underlying tools for sending messages that doesn't
depend on any work.models.
"""
import traceback

from django.conf import settings
from django.db import models
from util.timezone import now

from errors.models import log_error, notify
from front.models import Front, DeliveryErrorChecker
from work.models.work import Work
from rentals.models import SMSChannel
from util.email import EmailSender, EmailExceptionTryLater
from util.html_status_codes import ServerError, NotOkError


UNCLAIMED_CLEANING_IN_LT_48_HOURS = (  # Email
    'Unclaimed cleaning in less than 48 hours')
UNCLAIMED_CLEANING_IN_LT_24_HOURS = (  # Email
    'Unclaimed cleaning in less than 24 hours')
UNCLAIMED_CLEANING_IN_LT_4_HOURS = (  # Email
    'Unclaimed cleaning in less than 4 hours')
ONE_WORKER_1_TIME_SLOT_2_JOBS = (
    '1 worker, 1 time slot, 2 jobs')  # Email
GOOD_MORNING_TODAYS_JOBS = (
    'Good morning! Today\'s cleanings:')  # SMS
GOOD_MORNING_2ND_SMS = (
    'Second good morning SMS to today\'s service workers')  # SMS
START_10_MINUTES_LATE = (  # SMS
    'This cleaning was supposed to start 10 minutes ago:')
START_15_MINUTES_LATE = (  # Email
    'Their cleaning was supposed to start 15 minutes ago')
START_20_MINUTES_LATE = (  # Email
    'Their cleaning was supposed to start 20 minutes ago')
CLEANING_TAKING_TOO_LONG = (  # Email
    'This cleaning is taking too long')
CLEANING_NOT_FINISHED_CHECK_IN_IN_25_MINUTES = (  # Email
    'Cleaning not finished: Check-in in 25 minutes')
NOBODY_LEFT_TO_DO_A_JOB = (  # Email
    'Nobody left to do a job')
UNKNOWABLE_JOB_CREATION_ERROR = (  # Email
    'I don\'t know if this job actually got created')
CLEAN_CO_CLEANING_NEEDS_CLEANER_ASAP = (  # Email
    'A cleaning was canceled. Please reassign.')
NEW_CLEAN_CO_WORKER = (  # Email
    'A new cleaning company cleaner has been added')
CLEAN_CO_CLEANING_NOT_ASSIGNED_2_HOURS_BEFORE = (  # Email
    'An unassigned cleaning company cleaning is in 2 hours')
CLEAN_CO_CLEANING_NOT_ASSIGNED_3_HOURS_BEFORE = (  # Email
    'An unassigned cleaning is in 3 hours')
CLEAN_CO_CLEANING_NOT_ASSIGNED_18_HOURS_BEFORE = (  # Email
    'An unassigned cleaning is in 18 hours')
CLEAN_CO_CLEANING_NOT_ASSIGNED_24_HOURS_BEFORE = (  # Email
    'An unassigned cleaning is in 24 hours')
CLEAN_CO_CLEANING_NOT_DONE_BY_3_10 = (  # Email
    'A cleaning company cleaning isn\'t complete by 3:10')
CLEAN_CO_CLEANING_NOT_DONE_BY_3_00 = (  # Email
    'A cleaning isn\'t complete by 3pm')
NEVER_STARTED = (  # Email
    'Job was never started')
NEVER_COMPLETED = (  # Email
    'Job was started but never finished')
SKEPTICAL_CAN_FINISH_FLEXIBLE_ON_TIME = (  # Email
    'I doubt this flexible job can be finished on time')
NOT_STARTED_1_HOUR_AFTER_SHOULD_BE_DONE = (  # Email
    'This job should have been done an hour ago but it hasn\'t even been '
    'started')
CANT_FIND_RECEIPT_BUILDING_BY_NICKNAME = (
    'Unable to figure out what building this receipt is for')
CANT_FIND_RECEIPT_WORKER_BY_PHONE = (
    'Unable to figure out what worker submitted this receipt')
DELAYED_TICKET = (
    'Delayed ticket. Do you wish to reschedule?')
NEW_CLEANING_AVAILABLE = (
    'A new cleaning is available')
INFORM_OF_TICKET_COUNT_NO_SLA = (
    'Please look at these tickets because they lack an SLA')
HIGH_PRIORITY_TICKET_JOB_CANCELED = (
    'URGENT: High priority ticket job canceled')
JOB_ON_PROPERLY_AND_KEYS = (
    'Somebody is doing this job on keys AND on properly')
CHECKOUT_TIME_CHANGED_SO_REASSIGN = (
    'A check out changed so the cleaning must be reassigned')
NEW_RECEIPT = (
    'A new receipt was submitted for reimbursement')
CONFIRMED_NO_CLEANING = (
    'A confirmed reservation lacks a cleaning')
CLEANER_REPORTED_PROBLEM = (
    'A cleaner reported a problem during a cleaning')


# Keep this list in sync with the list above to keep the subject line admin
# functioning correctly.
MESSAGE_REASONS = [
    UNCLAIMED_CLEANING_IN_LT_48_HOURS,
    UNCLAIMED_CLEANING_IN_LT_24_HOURS,
    UNCLAIMED_CLEANING_IN_LT_4_HOURS,
    ONE_WORKER_1_TIME_SLOT_2_JOBS,
    GOOD_MORNING_TODAYS_JOBS,
    GOOD_MORNING_2ND_SMS,
    START_10_MINUTES_LATE,
    START_15_MINUTES_LATE,
    START_20_MINUTES_LATE,
    CLEANING_TAKING_TOO_LONG,
    CLEANING_NOT_FINISHED_CHECK_IN_IN_25_MINUTES,
    NOBODY_LEFT_TO_DO_A_JOB,
    UNKNOWABLE_JOB_CREATION_ERROR,
    CLEAN_CO_CLEANING_NEEDS_CLEANER_ASAP,
    NEW_CLEAN_CO_WORKER,
    CLEAN_CO_CLEANING_NOT_ASSIGNED_2_HOURS_BEFORE,
    CLEAN_CO_CLEANING_NOT_ASSIGNED_3_HOURS_BEFORE,
    CLEAN_CO_CLEANING_NOT_ASSIGNED_24_HOURS_BEFORE,
    CLEAN_CO_CLEANING_NOT_DONE_BY_3_10,
    CLEAN_CO_CLEANING_NOT_DONE_BY_3_00,
    NEVER_STARTED,
    NEVER_COMPLETED,
    SKEPTICAL_CAN_FINISH_FLEXIBLE_ON_TIME,
    NOT_STARTED_1_HOUR_AFTER_SHOULD_BE_DONE,
    CANT_FIND_RECEIPT_BUILDING_BY_NICKNAME,
    CANT_FIND_RECEIPT_WORKER_BY_PHONE,
    DELAYED_TICKET,
    NEW_CLEANING_AVAILABLE,
    INFORM_OF_TICKET_COUNT_NO_SLA,
    HIGH_PRIORITY_TICKET_JOB_CANCELED,
    JOB_ON_PROPERLY_AND_KEYS,
    CHECKOUT_TIME_CHANGED_SO_REASSIGN,
    NEW_RECEIPT,
    CONFIRMED_NO_CLEANING,
    CLEANER_REPORTED_PROBLEM]


REASON_CHOICES = [(reason, reason) for reason in MESSAGE_REASONS]


EMAIL = 'email'
SMS = 'sms'


class MessageSender(object):
  def __init__(
      self, front=Front(), email_sender=EmailSender(),
      delivery_error_checker=None):
    self.front = front
    self._email_sender = email_sender
    self._delivery_error_checker = (
        delivery_error_checker or DeliveryErrorChecker(
            self.front.front_api, self.front.error_logger))

  def create_and_send_email(self, to, reason, content, work):
    Message.objects.create_and_send_email(
        to, reason, content, work, message_sender=self)

  def send(self, message):
    """
    Use this, like,
    my_message_sender.send(Message.objects.create(
        to=to_email_address,
        reason=NEVER_STARTED, kind=EMAIL,
        subject=NEVER_STARTED,
        content=content, work=work, when=now()))
    """
    if message.kind == SMS:
      self._send_sms(message)
    elif message.kind == EMAIL:
      self._send_email(message)
    else:
      raise Exception(message.kind)

  def _send_sms(self, message):
    """ Unlike email, sms is sent from Front typically to worker phones. """
    if message.subject:
      raise Exception(
          'With SMS, I expect an empty subject. This has {}'.format(
              message.subject))
    building = message.work.get_child_class_instance().get_rental().building
    sms_channel = building.sms_staff_from
    if not sms_channel:
      message = (
          'Go to https://keys.hihoward.com/'
          'admin/rentals/building/{}/change/ and set the "Sms staff from"'
          'field.\n\nThat way, when I SMS cleaners I\'ll know who to send '
          'the SMS from.').format(building.pk)
      notify(
          settings.DEFAULT_BUILDING_ALERT_EMAIL,
          'Somebody go set the sms_staff_from field on this building',
          message=message)
      return
    message.from_channel = sms_channel
    try:
      got = self.front.send_sms(
          message.to, message.content, sms_channel.identifier)
      message.please_resend_due_to_server_error = False
      message.save()
    except ServerError:
      message.please_resend_due_to_server_error = True
      message.server_error_count += 1
      if message.server_error_count > 5:
        log_error(
            'Unusually high number of front server errors',
            '{} seen for message {}'.format(
                message.server_error_count, message.pk))
      message.save()
      return
    except NotOkError as ex:
      self._alert_handle_this_better(ex)
    try:
      message.delivery_error = self._delivery_error_checker.delivery_error(
          got)
    except ServerError:
      # Fine, whatever, it probably got through. Maybe some day I'll program up
      # a thing that loops back around and retries verification on these
      # messages.
      pass
    except NotOkError as ex:
      self._alert_handle_this_better(ex)

  def _send_email(self, message):
    """ These are sent via Mailgun from settings.SERVER_EMAIL to, typically,
    cleaning companies or our own internal staff emails, which are all managed
    in Front. """
    if not message.to:
      message.delivery_error = 'There\'s no email to send this to'
      message.save()
    else:
      # Front thinks about things in terms of one issue per thread, and a
      # thread has the same subject. But Bob starting a cleaning late on
      # Tuesday is really a different issue from Sue starting a cleaning late
      # on Thursday, so the subject lines need to be different. BTW I'm not
      # sending these FROM front, these are from Mailgun, but they're sent TO
      # Front inboxes.
      subject = message.subject
      if message.work:
        work = message.work.get_child_class_instance()
        subject = '{}. {} at {}'.format(
            subject, work.offered_start_time.date(),
            work.get_rental().nickname)
      try:
        self._email_sender.send_mail(
            subject, message.content, settings.SERVER_EMAIL,
            sorted(message.to.split(',')), reply_to=message.reply_to)
      except EmailExceptionTryLater:
        message.please_resend_due_to_server_error = True
        message.server_error_count += 1
        message.save()

  def _alert_handle_this_better(self, ex):
    log_error(
        'Handle this Error smarterer',
        'I refactored FrontAPI to throw exceptions on any not-ok '
        'response. I shouldn\'t be seeing it here though! I\'m only '
        'catching this here so it doesn\'t block all the other '
        'messages. Please handle this smarter. {}\n\n{}'.format(
            ex, traceback.format_exc()))


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
  def create_and_send_sms(
      self, to, reason, content, work, message_sender=None):
    """ This function doesn't save any space, really. You're welcome to just
    ignore it and do, like, message_sender.send(Message.objects.create(... """
    message_sender = message_sender or MessageSender()
    message_sender.send(self.create(
        to=to, reason=reason, kind=SMS,
        content=content, work=work, when=now()))

  def create_and_send_email(
      self, to, reason, content, work, subject=None, message_sender=None):
    message_sender = message_sender or MessageSender()
    subject = subject or SubjectLine.objects.get_subject_line(reason)
    message_sender.send(self.create(
        to=to, reason=reason, kind=EMAIL, subject=subject,
        content=content, work=work, when=now()))

  def existing_content_today(self, reason, nnow=None):
    nnow = nnow or now()
    return set([message.content for message in Message.objects.filter(
        when__date=nnow.date(), reason=reason)])


class Message(models.Model):
  when = models.DateTimeField(db_index=True)
  to = models.CharField(
      max_length=200, help_text='A comma delimited list of email addresses')
  reason = models.CharField(choices=REASON_CHOICES, max_length=100)
  kind = models.CharField(choices=KIND_SEND_MESSAGE_CHOICES, max_length=20)
  subject = models.TextField(blank=True, null=True, help_text=(
      'This only applies to emails.'))
  content = models.TextField()
  delivery_error = models.TextField(null=True, blank=True)
  work = models.ForeignKey(
      Work, on_delete=models.CASCADE, null=True, blank=True,
      related_name='message_set')
  from_channel = models.ForeignKey(
      SMSChannel, on_delete=models.CASCADE, null=True, blank=True)
  reply_to = models.CharField(
      max_length=200, default='', help_text=(
          'When the recipient replies to the email, where should it go?'))
  please_resend_due_to_server_error = models.BooleanField(
      default=False, help_text=(
          'You send a message, front throws a 502, that means we should just '
          'retry later.'))
  server_error_count = models.PositiveIntegerField(default=0, help_text=(
      'Pretty much out of curriosity, how many server errors did we hit '
      'trying to send this?'))

  objects = MessageManager()

  def send(self, message_sender=None):
    message_sender = message_sender or MessageSender()
    if not self.when:
      self.when = now()
    message_sender.send(self)
    self.save()

  class Meta:
    ordering = ('-when',)

  def __repr__(self):
    return '<Message {}: {} {} {}>'.format(
        self.pk, self.kind, self.when.date(),
        (self.subject or self.content)[:30])
