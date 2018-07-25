"""
This is all the stuff that applies to both guest SMSs and Emails, scheduling
for instance.
"""
from abc import abstractmethod
from datetime import timedelta, time

from django.conf import settings
from django.db import models
from django.utils.timezone import now

from reservations.models import Reservation
from util.channels import AIRBNB


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

  class Meta:
    abstract = True

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
          # We may have updated the wording of the messages.
          exist.message = template.message_for_reservation(reservation)
          # The guest may change their checkout date or something.
          # Note this may trigger a late SMS alert.
          exist.when_should = template.when_should(reservation)
          exist.save()
        to_return.append(exists[0])
      else:
        # Texts go out every hour, and only if they were supposed to go out
        # in the last 6 hours. So only allow a text to be created if it's
        # supposed to go out within the last 4 hours (or in the future).
        cutoff = now() - timedelta(
            settings.ALLOW_SMS_CATCH_UP_HOURS - 2)
        if template.when_should(reservation) > cutoff:
          to_return.append(template.create_for_reservation(reservation))
    return to_return


class Message(models.Model):
  """ And here's an actual message that will be sent to a guest. """
  reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE)
  # Now that we keep track of the template, we could move this to a getter.
  guesty_custom_field_id = models.CharField(
      null=True, blank=True, max_length=100, help_text=(
          'If this guesty custom field is set to False for this reservation, '
          'turn this message off.'))
  # Now that we keep track of the template, we could move this to a getter.
  check_before_sending = models.CharField(
      max_length=30, null=True, blank=True, choices=CHECK_BEFORE_SENDING)
  # The index on when_should is so _might_need_sending stays fast.
  when_should = models.DateTimeField(db_index=True)
  when_did = models.DateTimeField(null=True, blank=True)
  green_light = models.BooleanField(help_text=(
      'Admins have the power to turn off individual SMS messages.'))
  why_did_not_send = models.CharField(
      max_length=250, default='', help_text=(
          'This message came up to get sent, but it turned out we shouldn\'t '
          'have sent it. This is the reason why.'))
  created_at = models.DateTimeField(auto_now_add=True)
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

  @abstractmethod
  def get_template(self):
    raise NotImplementedError('Message.get_template')

  def explain_why_do_not_send(self):
    from id_verify.models import Submission
    if not self.reservation.confirmed():
      return 'The reservation is not confirmed.'
    if self.check_before_sending == ID_VERIFICATION_REQUIRED:
      if self.reservation.id_verified:
        return 'ID_VERIFICATION_REQUIRED but the id is verified already.'
      elif Submission.objects.filter(reservation=self.reservation):
        return 'ID_VERIFICATION_REQUIRED but an id submission exists.'
    if self.check_before_sending == MORNING_AFTER_ARRIVAL:
      if self.reservation.night_count == 1:
        return 'MORNING_AFTER_ARRIVAL and night_count == 1'
      id_etc = self._explain_why_id_paid_security_deposit_not_ok()
      if id_etc:
        return 'MORNING_AFTER_ARRIVAL {}'.format(id_etc)
    if self.check_before_sending == PAYMENT_DEPOSIT_ID_RECEIVED:
      id_etc = self._explain_why_id_paid_security_deposit_not_ok()
      if id_etc:
        return 'PAYMENT_DEPOSIT_ID_RECEIVED {}'.format(id_etc)

  def _explain_why_id_paid_security_deposit_not_ok(self):
    if self.reservation.listing.channel == AIRBNB:
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
      if field[0] == self.guesty_custom_field_id:
        return field[1]
