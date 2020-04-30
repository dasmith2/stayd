"""
This is all the stuff that applies to both guest SMSs and Emails, scheduling
for instance.
"""
from abc import abstractmethod
from datetime import timedelta, time

from django.conf import settings
from django.db import models
from util.timezone import now

from errors.models import Notifier, log_error
from front.models import EMAIL, PHONE
from guests.models import Guest
from guesty.custom_field_ids import GUESTY_MESSAGE_TOGGLE_CUSTOM_FIELDS
from reservations.models import Reservation
from util.channels import AIRBNB
from util.clock import Clock
from util.timezone import get_readable_duration


ID_VERIFICATION_REQUIRED = 'id_verification_required'
PAYMENT_DEPOSIT_ID_RECEIVED = 'payment_deposit_id_received'
MORNING_AFTER_ARRIVAL = 'morning_after_arrival'
ANY_CHANNEL_BESIDES_AIRBNB = 'any_channel_besides_airbnb'

CHECK_BEFORE_SENDING = (
    (ID_VERIFICATION_REQUIRED, 'ID verification still required'),
    (PAYMENT_DEPOSIT_ID_RECEIVED, (
        'Complete payment, deposit, ID verification, background check, and '
        'valid high risk')),
    (MORNING_AFTER_ARRIVAL, (
        '2 or more nights; payment, deposit, ID verification, background '
        'check, and valid high risk')),
    (ANY_CHANNEL_BESIDES_AIRBNB, (
        'Don\'t send this for Airbnb reservations')))

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
    (time(12), 'noon'),
    (time(14), '2:00pm'),
    (time(19), '7:00pm'))

# Triggers
FIRST_PAYMENT_DEPOSIT_ID_BG_CHECK_RECEIVED = (
    'FIRST_PAYMENT_DEPOSIT_ID_RECEIVED')
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
INVALID_IMAGE_UPLOAD = 'INVALID_IMAGE_UPLOAD'
GUEST_UPLOADED_US_ID_FRONT_ONLY = 'GUEST_UPLOADED_US_ID_FRONT_ONLY'
GUEST_UPLOADED_NON_US_ID = 'GUEST_UPLOADED_NON_US_ID'

TRIGGERING_EVENTS = (
    (FIRST_PAYMENT_DEPOSIT_ID_BG_CHECK_RECEIVED, (
        'First payment, deposit, ID verification, and background check '
        'received')),
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
        'Resend the ID verification link to a guest')),
    (INVALID_IMAGE_UPLOAD, 'The guests ID verification had an invalid image'),
    (GUEST_UPLOADED_US_ID_FRONT_ONLY, (
        'We also need the back of the guests US ID for a background check')),
    (GUEST_UPLOADED_NON_US_ID, (
        'The guest uploaded a non-US, non-passport ID')))


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
  active = models.BooleanField(default=True, help_text=(
      'You cant delete templates or theyll delete all existing messages. '
      'Simply inactivate templates you dont want.'))
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
          'This is the reason for the message. '
          'If the boolean guesty custom field for a reservation with this '
          'name is set to False, then the corresponding message should '
          'not send.'))

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

  def create_prescheduled_for_reservation(self, reservation, nnow=None):
    nnow = nnow or now()
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
        cutoff = nnow - timedelta(
            settings.ALLOW_SMS_CATCH_UP_HOURS - 1)
        if template.when_should(reservation) > cutoff:
          to_return.append(template.create_new_message(reservation))
    return to_return

  def get_for_reservation(self, reservation):
    return self.filter(reservation=reservation).select_related(
        'template').order_by('when_should')

  def notify_overdue_messages(
      self, clock=Clock(), notifier=Notifier(), verbose=False):
    overdues = self._way_overdue_for_sending(clock)
    if overdues:
      message = (
          'Use your best judgement to determine if these messages still need '
          'to go out, and how to deliver them if they do.\n\n{}').format(
              self._way_overdue_message(overdues, clock, verbose))
      notifier.notify(
          settings.ALERT_OVERDUE_MESSAGES,
          'Long overdue {}'.format(self.get_plural_name()), message)
      for overdue in overdues:
        overdue.notified_overdue_on = clock.now()
        overdue.save()

  def _way_overdue_for_sending(self, clock):
    definitely_overdue = []
    for possible in self.filter(
        when_should__gte=clock.now() - timedelta(days=3),
        when_should__lte=clock.now(),
        when_did=None, why_did_not_send='',
        template__allowed_hours_late__isnull=False,
        notified_overdue_on__isnull=True).select_related(
            'template').order_by('when_should'):
      # If the server went down for six hours or whatever, maybe we lucked
      # out and some of these messages that never got visited actually aren't
      # supposed to go out in the first place, so, no harm no foul.
      possible.why_did_not_send = possible.explain_why_do_not_send()
      possible.save()
      if not possible.why_did_not_send and possible.overdue(clock):
        definitely_overdue.append(possible)
    return definitely_overdue

  def _way_overdue_message(self, overdues, clock, verbose):
    entries = []
    for overdue in overdues:
      guest = overdue.reservation.guest
      message = (
          '{}\n{}\n{} {} {}, Check in {}\n{}\n'
          'Should have sent {} ago').format(
              overdue.guesty_custom_field_name(),
              overdue.reservation.admin_url(),
              overdue.get_send_to(),
              guest.full_name,
              overdue.reservation.rental.nickname,
              overdue.reservation.check_in_date_string(),
              overdue.describe_contents(),
              get_readable_duration(clock.now() - overdue.when_should))
      if verbose:
        print(message + '\n')
      entries.append(message)
    return '\n\n'.join(entries)

  def likely_to_send(self, from_date, to_date):
    for msg in self.filter(
        when_should__date__gte=from_date,
        when_should__date__lt=to_date).select_related(
            'reservation', 'reservation__rental',
            'reservation__guest', 'template').order_by(
                'when_should'):
      if msg.should_send() or msg.when_did:
        yield msg

  def need_sending(self, clock, verbose):
    return_me = []
    for message in self.filter(
        when_should__gte=clock.now() - timedelta(days=7),
        when_should__lte=clock.now(),
        when_did=None).select_related('template').order_by('when_should'):

      message.why_did_not_send = message.explain_why_do_not_send()
      message.save()
      if message.why_did_not_send:
        if verbose:
          print('Dont send "{}" to {} because {}'.format(
              message.describe_contents()[:30],
              message.reservation.guest.full_name,
              message.why_did_not_send))
      elif message.should_alert_if_late() and message.overdue(clock):
        if verbose:
          if message.why_did_not_send:
            print((
                '"{}" didnt send to {} because {}, which is no longer the '
                'case, but by now it\'s overdue.').format(
                    message.describe_contents_brief(),
                    message.reservation.guest.full_name,
                    message.why_did_not_send))
          else:
            print('Dont send "{}" to {} because it\'s overdue.'.format(
                message.describe_contents_brief(),
                message.reservation.guest.full_name))
      else:
        return_me.append(message)
    return return_me


class Message(models.Model):
  """ And here's an actual message that will be sent to a guest. """

  # The template field has to point to a non-abstract class, so for example,
  # look for SMS.template in guest_messages/models.py

  reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE)
  # The index on when_should is so need_sending stays fast.
  when_should = models.DateTimeField(db_index=True)
  when_did = models.DateTimeField(null=True, blank=True)
  notified_overdue_on = models.DateTimeField(null=True, blank=True, help_text=(
      'If a message didnt go out at all and then it was too late, a '
      'notification gets sent. This says when, allowing us to make sure '
      'we dont resend that notification.'))
  # This did get used, like, one time.
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
  delivery_error = models.CharField(
      max_length=200, null=True, blank=True, help_text=(
          'When you run the delivery check, put the results of '
          'get_delivery_error here.'))
  about_to_send = models.BooleanField(default=False, help_text=(
      'Set this to true, and then check about_to_send=True, when_did=None '
      'in order to see if this message is enqueued'))

  class Meta:
    abstract = True

  def describe_delay(self):
    if self.when_did:
      return get_readable_duration(self.when_did - self.when_should)
    if now() < self.when_should:
      return ''
    return get_readable_duration(now() - self.when_should) + ' (so far!)'

  def describe_contents_brief(self):
    return self.describe_contents()[:50]

  def guesty_custom_field_id(self):
    return self.template.guesty_custom_field_id

  def check_before_sending(self):
    return self.template.check_before_sending

  def get_child_class_instance(self):
    if self.__class__ != Message:
      # If you do select_related('message__sms'), then .message.sms won't
      # require an additional sql query. So far so good. But if you do
      # .message.sms.sms, it WILL require an additional SQL query.
      return self
    try:
      return self.sms
    except Message.sms.RelatedObjectDoesNotExist:
      pass
    try:
      return self.email
    except Message.email.RelatedObjectDoesNotExist:
      pass
    raise Exception(self)

  @abstractmethod
  def get_send_to(self):
    raise NotImplementedError('Message.get_send_to')

  @abstractmethod
  def describe_contents(self):
    raise NotImplementedError('Message.describe_contents')

  @abstractmethod
  def get_delivery_error(self, error_getter=None):
    raise NotImplementedError('Message.get_delivery_error')

  @abstractmethod
  def get_pretty_type(self):
    raise NotImplementedError('get_pretty_type')

  @abstractmethod
  def get_template(self):
    raise NotImplementedError('get_template')

  def should_send(self):
    return not self.explain_why_do_not_send()

  def should_alert_if_late(self):
    if self.template.allowed_hours_late and not self.template.triggering_event:
      return True
    elif not self.template.allowed_hours_late and (
        self.template.triggering_event):
      return False
    raise Exception(
        '{} {} has allowed_hours_late {} and triggering_event {}'.format(
            self.get_pretty_type, self.pk, self.template.allowed_hours_late,
            self.template.triggering_event))

  def overdue(self, clock):
    if not self.template.allowed_hours_late:
      # One time this happened. Trying to get to the bottom of it. Really
      # weird, by the time I get here the SMS no longer exists for some reason.
      log_error(
          'Asking overdue when the template has no allowed_hours_late?',
          'Figure out whats up with {} {} {} {} {} {} {} {}'.format(
              self.get_pretty_type(),
              self.pk,
              self.reservation,
              self.when_should,
              self.when_did,
              self.why_did_not_send,
              self.created_at,
              self.sent_to))
      return False
    cutoff = clock.now() - timedelta(hours=self.template.allowed_hours_late)
    return self.when_should < cutoff

  def explain_why_do_not_send(self):
    message = self.get_child_class_instance()
    if not message.get_send_to():
      return 'This guest doesn\'t have an {}'.format(
          message.get_name_of_thing_you_send_to())
    if not self.get_template().active:
      return 'The template is inactive'
    if not self.green_light:
      return 'The Guesty custom field for this particular message is off'
    if not self.reservation.confirmed():
      return 'The reservation is {} != confirmed.'.format(
          self.reservation.status)
    if not self.reservation.rental.is_active:
      return 'This reservation is for a rental that is no longer active'
    if self.check_before_sending() == ID_VERIFICATION_REQUIRED:
      if self.reservation.id_verified:
        return 'the id is verified already.'
      elif self.reservation.submission_set.exists():
        return 'an id submission exists.'
    if self.check_before_sending() == MORNING_AFTER_ARRIVAL:
      if self.reservation.get_night_count() == 1:
        return 'night count == 1'
      id_etc = self._explain_why_id_paid_security_bg_check_high_risk_not_ok()
      if id_etc:
        return '{}'.format(id_etc)
    if self.check_before_sending() == PAYMENT_DEPOSIT_ID_RECEIVED:
      id_etc = self._explain_why_id_paid_security_bg_check_high_risk_not_ok()
      if id_etc:
        return id_etc
    if self.check_before_sending() == ANY_CHANNEL_BESIDES_AIRBNB:
      if self.reservation.channel == AIRBNB:
        return 'This message doesn\'t apply to Airbnb'
    return ''

  def _explain_why_id_paid_security_bg_check_high_risk_not_ok(self):
    reasons = []
    if self.reservation.we_assume_cc_risk():
      if not self.reservation.is_paid_in():
        reasons.append('we haven\'t been paid')
    if self.reservation.we_take_security_deposit():
      if not self.reservation.has_security_deposit():
        reasons.append('there is no security deposit')
    # This isn't great, guest messages knowing about id verification and
    # background checks. This stuff belongs in a separate area to avoid
    # circular dependencies.
    if not self.reservation.id_verified:
      reasons.append('the ID isn\'t verified')
    if not self.reservation.background_check_valid():
      reasons.append('the background check is non-valid')  # Purposefully vague
    risk_score = self.reservation.riskscore_or_none
    if risk_score and risk_score.reservation_requires_approval() and (
        not risk_score.reservation_approved()):
      reasons.append('this risky reservation requires approval')
    return ', '.join(reasons)

  def guesty_custom_field_name(self):
    if not self.guesty_custom_field_id():
      return '-'
    for guesty_field_id, field_name in GUESTY_MESSAGE_TOGGLE_CUSTOM_FIELDS:
      if guesty_field_id == self.guesty_custom_field_id():
        return field_name
    return '{} no longer exists so I don\'t know what it\'s called'.format(
        self.guesty_custom_field_id())


class BadContactInfoManager(models.Manager):
  def handle_bad_contact_info_exception(self, ex, reservation, notifier=None):
    notifier = notifier or Notifier()
    handle = reservation.guest.phone
    subject_format = 'Bad phone number probably: {}'
    if ex.handle_type == EMAIL:
      handle = reservation.guest.email
      subject_format = 'Bad email address probably: {}'
    kwargs = {
        'handle': handle,
        'handle_type': ex.handle_type,
        'guest': reservation.guest}
    if not self.filter(**kwargs).exists():
      message = (
          'Information for VAs:\n\n{}\n{}\n\n'
          'Information for developers:\n\nSending {} caused {}').format(
              reservation.guest.full_name, reservation.admin_url(),
              ex.sent_data, ex.received_data)
      notifier.notify(
          settings.ALERT_BAD_PHONE, subject_format.format(handle), message)
      self.create(**kwargs)


HANDLE_TYPE_CHOICES = (
    (EMAIL, EMAIL),
    (PHONE, PHONE))


class BadContactInfo(models.Model):
  """ Wrong numbers and emails. Keep track of these so we only alert about
  them once. """
  handle = models.CharField(max_length=200, help_text=(
      'The literal email or phone number thats no good.'))
  handle_type = models.CharField(max_length=10, choices=HANDLE_TYPE_CHOICES)
  guest = models.ForeignKey(Guest, on_delete=models.CASCADE)

  objects = BadContactInfoManager()
