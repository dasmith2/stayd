"""
This is all the stuff that applies to both guest SMSs and Emails, scheduling
for instance.
"""
from abc import abstractmethod
from datetime import timedelta, time

from django.conf import settings
from django.db import models
from django.utils.timezone import now

from errors.models import ErrorLogger
from reservations.models import Reservation
from util.channels import AIRBNB
from util.clock import Clock
from util.timezone import utc_dt_to_tz_dt


ID_VERIFICATION_REQUIRED = 'id_verification_required'
PAYMENT_DEPOSIT_ID_RECEIVED = 'payment_deposit_id_received'
MORNING_AFTER_ARRIVAL = 'morning_after_arrival'

CHECK_BEFORE_SENDING = (
    (ID_VERIFICATION_REQUIRED, 'ID verification still required'),
    (PAYMENT_DEPOSIT_ID_RECEIVED, (
        'Payment, deposit, and ID verification received')),
    (MORNING_AFTER_ARRIVAL, (
        '2 or more nights; payment, deposit, and ID verification received')))


# The ones with real guesty ids are copied (by hand, ugh) from
# https://app.guesty.com/account/system/custom-fields
# haha ok they hid these ids in their latest refresh! So now, you gotta find
# an example reservation. Save the custom fields once just to make sure
# everything is synced up (otherwise you're liable to find 4 ids haha) Now
# pull that reservation down from the API, keep track of the
# existing custom fields, change the custom field in question, re-pull down
# that reservation from the API, and cross reference the new custom fields
# with the old ones. Hopefully there is exactly one field that changed, whose
# id goes here.
LAST_NAME_ID_RES_DO_NOT_MATCH = 'LAST_NAME_ID_RES_DO_NOT_MATCH'
FIRST_LAST_NAME_ID_CC_DO_NOT_MATCH = 'FIRST_LAST_NAME_ID_CC_DO_NOT_MATCH'
LAST_4_BRAND_CC_RES_DO_NOT_MATCH = 'LAST_4_BRAND_CC_RES_DO_NOT_MATCH'
NO_NAMES_MATCH = 'NO_NAMES_MATCH'
LAST_NAME_ID_RES_LAST_4_BRAND_CC_DO_NOT_MATCH = (
    'LAST_NAME_ID_RES_LAST_4_BRAND_CC_DO_NOT_MATCH')
FULL_NAME_CC_ID_LAST_4_BRAND_CC_DO_NOT_MATCH = (
    'FULL_NAME_CC_ID_LAST_4_BRAND_CC_DO_NOT_MATCH')
CC_ID_EVERYTHING_WRONG = 'CC_ID_EVERYTHING_WRONG'

RESEND_ID_VERIFICATION_LINK = 'RESEND_ID_VERIFICATION_LINK'

GUESTY_MESSAGE_TOGGLE_CUSTOM_FIELDS = (
    ('5afec8950c6ec3001f42e5b4', (
        'Request to complete ID verification (SMS- 3 hrs after booking)')),
    ('5afec8950c6ec3001f42e5b2', (
        'Reminder to complete ID verification (SMS- 26 hrs after booking)')),
    ('5afa2c379ebb42009e34f270', (
        'SMS reminder to fill out arrival form (5 days before '
        'check-in)')),
    ('5afa2c379ebb42009e34f26f', (
        'Check-in instructions email (3 days before check-in)')),
    ('5afa2c379ebb42009e34f26e', (
        'SMS confirming guest received check-in instructions '
        '(2 days before check-in)')),
    ('5afa2c379ebb42009e34f26d', 'Day of check-in SMS'),
    ('5afa2c379ebb42009e34f26c', (
        '"How\'s everything at the apartment?" SMS '
        '(morning after arrival)')),
    ('5afa2c379ebb42009e34f26b', (
        'Checkout instructions email (day before checkout)')),
    ('5afa2c379ebb42009e34f26a', 'Morning of checkout SMS'),
    ('5afa2c379ebb42009e34f269', (
        'Review request SMS (post checkout after cleaning)')),
    ('5b299253f2177301cca1269a', (
        'Guest feedback request (SMS 3 days after checkout)')))

DAYS = 'days'
HOURS = 'hours'
DAYS_OR_HOURS = ((DAYS, DAYS), (HOURS, HOURS))

BEFORE = 'before'
AFTER = 'after'
BEFORE_OR_AFTER = ((BEFORE, BEFORE), (AFTER, AFTER))

BOOKING = 'booking'
CHECKIN = 'checkin'
CHECKOUT = 'checkout'
PRESCHEDULED_EVENTS = (
    (BOOKING, BOOKING), (CHECKIN, CHECKIN), (CHECKOUT, CHECKOUT))

AT_TIME_CHOICES = (
    (time(9), '9:00am'),
    (time(19), '7:00pm'))

TRIGGERING_EVENTS = (
    (LAST_NAME_ID_RES_DO_NOT_MATCH, (
        'Last name on ID and reservation don\'t match')),
    (FIRST_LAST_NAME_ID_CC_DO_NOT_MATCH, (
        'The first and last names on the ID and CC don\'t match')),
    (LAST_4_BRAND_CC_RES_DO_NOT_MATCH, (
        'The last 4 digits and the brand of the CC and reservation don\'t '
        'match')),
    (NO_NAMES_MATCH, (
        'Last name on id and res, full name on id and cc all don\'t match')),
    (LAST_NAME_ID_RES_LAST_4_BRAND_CC_DO_NOT_MATCH, (
        'Last name on id and res, last 4 and cc brand don\'t match')),
    (FULL_NAME_CC_ID_LAST_4_BRAND_CC_DO_NOT_MATCH, (
        'Full names on id and cc, last 4 and cc brand don\'t match')),
    (CC_ID_EVERYTHING_WRONG, (
        'Last name id res, full name id cc, last 4, all wrong.')),
    (RESEND_ID_VERIFICATION_LINK, (
        'Resend the ID verification link to a guest')))


class TemplateManager(models.Manager):
  pass


class Template(models.Model):
  """ Some messages are pre-scheduled, and some messages are triggered
  by an event. """
  # Fields that have to do with messages that are triggered by an event.
  triggering_event = models.CharField(
      null=True, blank=True, max_length=200, choices=TRIGGERING_EVENTS,
      help_text='What event triggers this message?')

  # Fields that have to do with messages that are scheduled ahead of time.
  pre_scheduled = models.BooleanField(default=True, help_text=(
      'Is this message scheduled ahead of time?'))
  preschedule_around = models.CharField(
      null=True, blank=True, max_length=8, choices=PRESCHEDULED_EVENTS,
      help_text=(
          'Do offset_hours and before_or_after refer to checkin or checkout?'))
  offset = models.PositiveIntegerField(null=True, blank=True, help_text=(
      'How many days or hours from the checkin or checkout should these '
      'messages be sent?'))
  days_or_hours = models.CharField(
      null=True, blank=True, max_length=5, choices=DAYS_OR_HOURS, help_text=(
          'Does offset refer to days or hours?'))
  before_or_after = models.CharField(
      null=True, blank=True, max_length=6, choices=BEFORE_OR_AFTER, help_text=(
          'Should these be sent before or after?'))
  at_time = models.TimeField(
      blank=True, null=True, choices=AT_TIME_CHOICES, help_text=(
          'You can set a specific time of day for these messages to go out.'))
  check_before_sending = models.CharField(
      max_length=30, null=True, blank=True, choices=CHECK_BEFORE_SENDING)
  allowed_hours_late = models.PositiveIntegerField(
      null=True, blank=True, help_text=(
          'It was supposed to go out a while ago. Is it too late to send '
          'now?'))
  guesty_custom_field_id = models.CharField(
      max_length=100, null=True, blank=True,
      choices=GUESTY_MESSAGE_TOGGLE_CUSTOM_FIELDS, help_text=(
          'If the boolean guesty custom field for a reservation with this '
          'name is set to False, then the corresponding message should '
          'turn off the green light.'))

  # DON'T do objects = TemplateManager(). The managers get set in
  # models.py which contain base classes.

  @abstractmethod
  def create_new_message(self, reservation):
    raise NotImplementedError('create_new_message')

  def setup_new_message(self, reservation, new_message):
    """ This is the shared stuff for EmailTemplate#create_new_message and
    SMSTemplate#create_new_message. """
    new_message.reservation = reservation
    new_message.when_should = self.when_should(reservation)
    new_message.green_light = True
    new_message.template = self
    new_message.save()
    return new_message

  @abstractmethod
  def update_existing_message(self, exist):
    """ This is really more like, update the parts of the existing message
    that are particular to this class. MessageManager.update_existing_message
    has the shared stuff. """
    raise NotImplementedError('update_existing_message')

  def setup_existing_message(self, exist):
    """ This is the shared stuff so EmailTemplate#update_existing_message and
    SMSTemplate#update_existing_message can simplify. """
    # The guest may change their checkout date or something.
    # Note this may trigger a late SMS alert.
    exist.when_should = self.when_should(exist.reservation)
    exist.save()
    return exist

  class Meta:
    abstract = True
    ordering = ['pk']

  def when_should(self, reservation):
    if not self.pre_scheduled:
      return now()
    if self.days_or_hours == DAYS:
      delta = timedelta(days=self.offset)
    else:
      delta = timedelta(hours=self.offset)
    if self.before_or_after == BEFORE:
      delta = -delta
    if self.preschedule_around == CHECKIN:
      on = reservation.get_check_in() + delta
    elif self.preschedule_around == CHECKOUT:
      on = reservation.get_check_out() + delta
    else:
      on = reservation.get_booked_at() + delta
    if self.at_time:
      # This works because get_check_in and get_check_out return with
      # the tzinfo set to the tz of the rental. So if at_time is 9am,
      # this will do 9am in whatever timezone the rental is in.
      on = on.replace(
          hour=self.at_time.hour, minute=self.at_time.minute, second=0,
          microsecond=0)
    return on


class MessageManager(models.Manager):
  @abstractmethod
  def get_prescheduled_templates(self):
    raise NotImplementedError('MessageManager.get_prescheduled_templates')

  @abstractmethod
  def get_plural_name(self):
    raise NotImplementedError('Messagemanager.get_plural_name')

  def create_prescheduled_for_reservation(self, reservation):
    existing = self.get_for_reservation(reservation)
    templates = self.get_prescheduled_templates()
    for exist in existing:
      if not [t for t in templates if t == exist.template]:
        if not exist.when_did:  # No sense deleting one that was sent already.
          exist.delete()
    to_return = []
    for template in templates:
      exists = [e for e in existing if e.template == template]
      if exists:
        exist = exists[0]
        if not exist.when_did:  # No sense updating one that was sent already.
          template.update_existing_message(exist)
        to_return.append(exist)
      else:
        # Texts go out every hour, hence -1, otherwise we'll just be creating
        # messages that could never go out in the first place.
        cutoff = now() - timedelta(
            settings.ALLOW_SMS_CATCH_UP_HOURS - 1)
        if template.when_should(reservation) > cutoff:
          to_return.append(template.create_new_message(reservation))
    return to_return

  def get_for_reservation(self, reservation):
    return self.filter(reservation=reservation).order_by('when_should')

  def notify_overdue_messages(
      self, clock=Clock(), error_logger=ErrorLogger(), verbose=False):
    overdues = self._way_overdue_for_sending(clock)
    if overdues:
      message = (
          'These {} didn\'t go out on time and must now be handled '
          'manually:\n\n{}').format(
              self.get_plural_name(), self._way_overdue_message(
                  overdues, clock, verbose))
      error_logger.log_error(
          'Long overdue {}'.format(
              self.get_plural_name()), message, always_new_error=True)
      self._overdue_dealt_with(overdues, clock)

  def _way_overdue_for_sending(self, clock):
    definitely_overdue = []
    for possible in self.filter(
        when_should__gte=clock.now() - timedelta(days=3),
        when_should__lte=clock.now(),
        when_did=None, why_did_not_send='').select_related(
        'template').order_by('when_should'):
      # If the server went down for six hours or whatever, maybe we lucked
      # out and some of these messages that never got visited actually aren't
      # supposed to go out in the first place, so, no harm no foul.
      reason_why_not = possible.explain_why_do_not_send()
      if reason_why_not:
        possible.why_did_not_send = reason_why_not
        possible.save()
      elif possible.overdue(clock):
        definitely_overdue.append(possible)
    return definitely_overdue

  def _way_overdue_message(self, overdues, clock, verbose):
    entries = []
    for overdue in overdues:
      guest = overdue.reservation.guest
      message = (
          '{} {} {} Reservation id {}\n{}\n'
          'Should have sent {} hours ago').format(
              overdue.sent_to,
              guest.full_name,
              overdue.reservation.rental.nickname,
              overdue.reservation.pk,
              overdue.describe_contents(),
              int((clock.now() - overdue.when_should).seconds / 3600))
      if verbose:
        print(message + '\n')
      entries.append(message)
    return '\n\n'.join(entries)

  def _overdue_dealt_with(self, overdues, clock):
    for overdue in overdues:
      overdue.why_did_not_send = (
          'I notified the admins about this overdue message on {}'.format(
              utc_dt_to_tz_dt(clock.now())))
      overdue.save()

  def need_sending(self, sync, clock, verbose):
    return_me = []
    for message in self.filter(
        when_should__gte=clock.now() - timedelta(days=7),
        when_should__lte=clock.now(),
        when_did=None).select_related('template').order_by('when_should'):
      # We discovered Guesty doesn't send a webhook update
      # for a reservation when payments are received. Payments affect
      # is_paid_in which affect whether or not messages are sent. So we
      # must sync all affected reservations first. This is really ugly.
      # guest_messages cares about syncing reservations now?! And we
      # gotta do all these Guesty round trips? ugh.
      sync.sync_stayd_reservation(message.reservation)

      why_not_send = message.explain_why_do_not_send()
      if why_not_send:
        message.why_did_not_send = why_not_send
        message.save()
        if verbose:
          print('Dont send "{}" to {} because {}'.format(
              message.message[:30],
              message.reservation.guest.full_name,
              why_not_send))
      elif message.overdue(clock):
        if verbose:
          if message.why_did_not_send:
            print((
                '"{}" didnt send to {} because {}, which is no longer the '
                'case, but by now it\'s overdue.').format(
                    message.message[:30], message.reservation.guest.full_name,
                    message.why_did_not_send))
          else:
            print('Dont send "{}" to {} because it\'s overdue.'.format(
                message.message[:30],
                message.reservation.guest.full_name))
      else:
        return_me.append(message)
    return return_me

  def need_to_verify_delivery(self):
    return self.filter(
        delivery_check_on=None, send_results__isnull=False,
        when_should__gt=now() - timedelta(days=7)).order_by('when_did')

  def verify_delivery_helper(
      self, get_delivery_error_arg, error_logger, verbose,
      problem_email_subject):
    problems = []
    for msg in self.need_to_verify_delivery():
      msg.delivery_error = msg.get_delivery_error(get_delivery_error_arg)
      if msg.delivery_error:
        current_send_to = msg.get_send_to()
        send_to_change_msg = ''
        if current_send_to != msg.sent_to:
          send_to_change_msg = 'note: the guest\'s {} is now {}\n'.format(
              msg.get_name_of_thing_you_send_to(), current_send_to)
        problem = '{}\n{}\nsent to: {}\n{}error: {}\n{}'.format(
            msg.reservation.guest.get_name(),
            msg.reservation.guesty_url(),
            msg.sent_to,
            send_to_change_msg,
            msg.delivery_error,
            msg.describe_contents())
        problems.append(problem)
        if verbose:
          print(problem)
      msg.delivery_check_on = now()
      msg.save()
    if problems:
      error_logger.log_error(
          problem_email_subject,
          '\n\n'.join(problems),
          extra_to=settings.ALERT_BAD_PHONE,
          always_new_error=True)


class Message(models.Model):
  """ And here's an actual message that will be sent to a guest. """

  # The template field has to point to a non-abstract class, so for example,
  # look for SMS.template in guest_messages/models.py

  reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE)
  # The index on when_should is so need_sending stays fast.
  when_should = models.DateTimeField(db_index=True)
  when_did = models.DateTimeField(null=True, blank=True)
  green_light = models.BooleanField(help_text=(
      'Admins have the power to turn off individual SMS messages.'))
  why_did_not_send = models.CharField(
      max_length=250, default='', help_text=(
          'This message came up to get sent, but it turned out we shouldn\'t '
          'have sent it. This is the reason why.'))
  created_at = models.DateTimeField(auto_now_add=True)
  sent_to = models.CharField(
      max_length=100, null=True, blank=True, help_text=(
          'If we tried to send this message, what number or email did we try '
          'to send it to?'))
  send_results = models.TextField(null=True, blank=True, help_text=(
      'The text from attempting to send this message. Note that this '
      'is just whether or not the request was well formed and front was '
      'able to enque the message to be sent. If the number was invalid, '
      'that won\'t become obvious until we circle back around and see '
      'if there was a delivery error.'))
  delivery_check_on = models.DateTimeField(null=True, blank=True)
  delivery_error = models.CharField(
      max_length=200, null=True, blank=True, help_text=(
          'When you run the delivery check, put the results of '
          'get_delivery_error here.'))

  class Meta:
    abstract = True

  def guesty_custom_field_id(self):
    return self.template.guesty_custom_field_id

  def check_before_sending(self):
    return self.template.check_before_sending

  @abstractmethod
  def get_send_to(self):
    raise NotImplementedError('Message.get_send_to')

  @abstractmethod
  def describe_contents(self):
    raise NotImplementedError('Message.describe_contents')

  @abstractmethod
  def get_delivery_error(self, error_getter=None):
    raise NotImplementedError('Message.get_delivery_error')

  def should_send(self):
    return not self.explain_why_do_not_send()

  def overdue(self, clock):
    cutoff = clock.now() - timedelta(hours=self.template.allowed_hours_late)
    return self.when_should < cutoff

  def explain_why_do_not_send(self):
    from id_verify.models import Submission
    if not self.reservation.confirmed():
      return 'The reservation is {} != confirmed.'.format(
          self.reservation.status)
    if self.check_before_sending() == ID_VERIFICATION_REQUIRED:
      if self.reservation.id_verified:
        return 'ID_VERIFICATION_REQUIRED but the id is verified already.'
      elif Submission.objects.filter(reservation=self.reservation):
        return 'ID_VERIFICATION_REQUIRED but an id submission exists.'
    if self.check_before_sending() == MORNING_AFTER_ARRIVAL:
      if self.reservation.night_count == 1:
        return 'MORNING_AFTER_ARRIVAL and night_count == 1'
      id_etc = self._explain_why_id_paid_security_deposit_not_ok()
      if id_etc:
        return 'MORNING_AFTER_ARRIVAL {}'.format(id_etc)
    if self.check_before_sending() == PAYMENT_DEPOSIT_ID_RECEIVED:
      id_etc = self._explain_why_id_paid_security_deposit_not_ok()
      if id_etc:
        return 'PAYMENT_DEPOSIT_ID_RECEIVED {}'.format(id_etc)

  def _explain_why_id_paid_security_deposit_not_ok(self):
    if self.reservation.channel == AIRBNB:
      if not self.reservation.id_verified:
        return 'ID isn\'t verified'
    else:
      reasons = []
      if not self.reservation.id_verified:
        reasons.append('ID isn\'t verified')
      if not self.reservation.is_paid_in:
        reasons.append('Not paid')
      if not self.reservation.has_security_deposit():
        reasons.append('No security deposit')
      return ', '.join(reasons)

  def guesty_custom_field_name(self):
    for field in GUESTY_MESSAGE_TOGGLE_CUSTOM_FIELDS:
      if field[0] == self.guesty_custom_field_id():
        return field[1]
