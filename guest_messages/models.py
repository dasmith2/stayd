import abc
import ast
from collections import namedtuple
from datetime import timedelta, time
import re

from django.conf import settings
from django.db import models
from django.utils.timezone import now

from errors.models import log_error, ErrorLogger
from reservations.models import Reservation
from util.channels import AIRBNB, BOOKINGCOM, HOMEAWAY, GUESTY
from util.clock import Clock
from util.timezone import utc_dt_to_tz_dt
from front.models import Front


ID_VERIFICATION_REQUIRED = 'id_verification_required'
PAYMENT_DEPOSIT_ID_RECEIVED = 'payment_deposit_id_received'
MORNING_AFTER_ARRIVAL = 'morning_after_arrival'
SPECIAL_PURPOSES = (
    (ID_VERIFICATION_REQUIRED, 'ID verification required'),
    (PAYMENT_DEPOSIT_ID_RECEIVED, (
        'Payment, deposit, and ID verification received')),
    (MORNING_AFTER_ARRIVAL, 'Morning after arrival, 2 or more nights'))


DAYS = 'days'
HOURS = 'hours'
DAYS_OR_HOURS = ((DAYS, DAYS), (HOURS, HOURS))

BEFORE = 'before'
AFTER = 'after'
BEFORE_OR_AFTER = ((BEFORE, BEFORE), (AFTER, AFTER))

BOOKING = 'booking'
CHECKIN = 'checkin'
CHECKOUT = 'checkout'
TRIGGERING_EVENT = (
    (BOOKING, BOOKING), (CHECKIN, CHECKIN), (CHECKOUT, CHECKOUT))

""" Custom template tags. See templates/admin/guest_message_templates.html
for how they're used. """
GUEST_FIRST_NAME = 'guest_first_name'
ADDRESS = 'address'
AIRBNB_OPEN = AIRBNB
BOOKINGCOM_OPEN = BOOKINGCOM
HOMEAWAY_OPEN = HOMEAWAY
TAG_CLOSE = '/'
DELAY = 'delay'
CITY = 'city'
ID_VERIFY_LINK = 'id_verify_link'
GUEST_EMAIL = 'guest_email'
CHANNEL = 'channel'
CHECKOUT_TIME = 'checkout_time'


class ReservationSyncer(object):
  @abc.abstractmethod
  def sync_stayd_reservation(self, reservation):
    raise NotImplementedError('sync_stayd_reservation')


class SMSTemplateManager(models.Manager):
  def get_all_in_order(self):
    # I used to do something real fancy here with checkin comes before
    # checkout and so on. But then the forms couldn't juggle the ids
    # properly and everything got corrupted. So, just keep it simple
    # and annoying I guess.
    return self.all().order_by('pk')

  def create_for_reservation(self, guesty_custom_field_id, reservation):
    template = SMSTemplate.objects.get(
        guesty_custom_field_id=guesty_custom_field_id)
    return template.create_for_reservation(reservation)


AT_TIME_CHOICES = (
    (time(9), '9:00am'),
    (time(19), '7:00pm'))


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
EVERYTHING_WRONG = 'EVERYTHING_WRONG'

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
        'Guest feedback request (SMS 3 days after checkout)')),
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
    (EVERYTHING_WRONG, (
        'Last name id res, full name id cc, last 4, all wrong.')),
    (RESEND_ID_VERIFICATION_LINK, (
        'Resend the ID verification link to a guest')))


class SMSTemplate(models.Model):
  """ Here's where we group the configurable settings for a template. """
  guesty_custom_field_id = models.CharField(
      max_length=100, unique=True,
      choices=GUESTY_MESSAGE_TOGGLE_CUSTOM_FIELDS, help_text=(
          'If the boolean guesty custom field for a reservation with this '
          'name is set to False, then the corresponding message should '
          'turn off the green light.'))
  special_purpose = models.CharField(
      max_length=30, null=True, blank=True, choices=SPECIAL_PURPOSES)
  offset = models.PositiveIntegerField(null=True, blank=True, help_text=(
      'How many days or hours from the checkin or checkout should these '
      'messages be sent?'))
  days_or_hours = models.CharField(
      null=True, blank=True, max_length=5, choices=DAYS_OR_HOURS, help_text=(
          'Does offset refer to days or hours?'))
  before_or_after = models.CharField(
      null=True, blank=True, max_length=6, choices=BEFORE_OR_AFTER, help_text=(
          'Should these be sent before or after?'))
  triggering_event = models.CharField(
      null=True, blank=True, max_length=8, choices=TRIGGERING_EVENT,
      help_text=(
          'Do offset_hours and before_or_after refer to checkin or checkout?'))
  at_time = models.TimeField(
      blank=True, null=True, choices=AT_TIME_CHOICES, help_text=(
          'You can set a specific time of day for these messages to go out.'))
  message = models.TextField(help_text=(
      'The actual message that will be copied for every reservation.'))
  pre_scheduled = models.BooleanField(default=True, help_text=(
      'Should a message be created from this template for every new '
      'reservation?'))

  objects = SMSTemplateManager()

  class Meta:
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
    if self.triggering_event == CHECKIN:
      on = reservation.get_check_in() + delta
    elif self.triggering_event == CHECKOUT:
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

  def message_for_reservation(self, reservation):
    message = self.message
    guest = reservation.guest
    message = self._simple_message_sub(
        GUEST_FIRST_NAME, guest.first_name or guest.full_name, message)
    message = self._simple_message_sub(
        ADDRESS, reservation.listing.rental.airbnb_address_scrape, message)
    message = self._simple_message_sub(
        CITY, reservation.listing.rental.city, message)
    message = self._simple_message_sub(
        ID_VERIFY_LINK, reservation.verify_id_url(), message)
    email = reservation.guest.email or reservation.anonymized_email
    message = self._simple_message_sub(GUEST_EMAIL, email, message)
    message = self._simple_message_sub(
        CHANNEL, reservation.display_channel or reservation.listing.channel,
        message)
    message = self._simple_message_sub(
        CHECKOUT_TIME, reservation.check_out_time_string(), message)

    keep_tag = reservation.listing.channel
    remove_tags = [AIRBNB, BOOKINGCOM, HOMEAWAY, GUESTY]
    remove_tags.remove(keep_tag)

    message = re.sub(
        r'{' + keep_tag + '}(.+?){/}', r'\1', message, flags=re.IGNORECASE)
    for remove_tag in remove_tags:
      message = re.sub(
          r'{' + remove_tag + '}.+?{/}', '', message, flags=re.IGNORECASE)
    return message

  def _simple_message_sub(self, tag_name, replacement, message):
    return re.sub(
        '{' + tag_name + '}', replacement, message, flags=re.IGNORECASE)

  def create_for_reservation(self, reservation):
    return SMS.objects.create(
        reservation=reservation,
        guesty_custom_field_id=self.guesty_custom_field_id,
        special_purpose=self.special_purpose,
        when_should=self.when_should(reservation),
        green_light=True,
        message=self.message_for_reservation(reservation))

  def _matches(self, guest_message):
    message_field = guest_message.guesty_custom_field_id
    return self.guesty_custom_field_id == message_field


class SMSManager(models.Manager):
  # Just a little bookkeeping class here for the send function.
  MessageList = namedtuple(
      'MessageList', 'guest_message phone messages')

  def get_for_reservation(self, reservation):
    return self.filter(reservation=reservation).order_by('when_should')

  def create_for_reservation(self, reservation):
    existing = self.get_for_reservation(reservation)
    templates = SMSTemplate.objects.filter(pre_scheduled=True)
    for exist in existing:
      if not [t for t in templates if t._matches(exist)]:
        if not exist.when_did:  # No sense deleting one that was sent already.
          exist.delete()
    to_return = []
    for template in templates:
      exists = [e for e in existing if e._matches(template)]
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

  def send(
      self, sync=None, message_pk=None, front=Front(), clock=Clock(),
      verbose=False):
    send_these = []
    sent_these = []
    if message_pk:
      messages = self.filter(pk=message_pk)
    else:
      messages = self._might_need_sending()
    for guest_message in messages:
      # We discovered Guesty doesn't necessarily send a webhook update
      # for a reservation when payments are received. Payments affect
      # is_paid_in which affect whether or not messages are sent. So we
      # must sync all affected reservations first. guest_messages caring
      # about guesty is pretty ugly though.
      if not message_pk:
        sync.sync_stayd_reservation(guest_message.reservation)
      why_not_send = guest_message.explain_why_do_not_send()
      if why_not_send:
        guest_message.why_did_not_send = why_not_send
        guest_message.save()
        if verbose:
          print('Dont send "{}" to {} because {}'.format(
              guest_message.message[:30],
              guest_message.reservation.guest.full_name,
              why_not_send))
      else:
        phone = guest_message.reservation.guest.phone
        messages = guest_message.message.split('{' + DELAY + '}')
        messages = [m.strip() for m in messages]
        send_these.append(
            SMSManager.MessageList(guest_message, phone, messages))
        sent_these.append(guest_message)
    if verbose:
      print(
          '{} messages to send (not including delays)'.format(len(send_these)))
    sent_count = len(send_these)
    clock.start()
    took_too_long = 0
    while send_these:
      send_these = self._send_first_and_return_next(send_these, front, verbose)
      if send_these:
        time_it_took = clock.elapsed_seconds()
        sleep_for = 45 - time_it_took
        if sleep_for > 0:
          clock.sleep(sleep_for)
        else:
          took_too_long = time_it_took
        clock.start()
    for guest_message in sent_these:
      guest_message.when_did = now()
      guest_message.save()
    if took_too_long:
      log_error('Sending {} SMSs took {} seconds'.format(
          sent_count, took_too_long), (
          'That\'s starting to get a little long. We ought to rework '
          'guest_messages/models.py#SMSManager.send to use threads '
          'or something.'))

  def need_to_verify_delivery(self):
    return self.filter(
        delivery_check_on=None, send_results__isnull=False,
        when_should__gt=now() - timedelta(days=3)).order_by('when_did')

  def verify_delivery(
      self, front=Front(), error_logger=ErrorLogger(), verbose=False):
    problems = []
    for msg in self.need_to_verify_delivery():
      msg.delivery_error = msg.get_delivery_error(front)
      if msg.delivery_error:
        # At this point, sent_to_phone is a new field and not necessarily
        # populated. Once this has been out for a few days this can be
        # simplified.
        phone = msg.sent_to_phone
        if not phone:
          phone = msg.reservation.guest.phone
        elif phone != msg.reservation.guest.phone:
          phone += '\nnote: the guest\'s phone number is now {}'.format(
              msg.reservation.guest.phone)
        problem = '{}\n{}\nsent to: {}\nerror: {}\n{}'.format(
            msg.reservation.guest.get_name(),
            msg.reservation.guesty_url(),
            phone,
            msg.delivery_error,
            msg.message)
        problems.append(problem)
        if verbose:
          print(problem)
      msg.delivery_check_on = now()
      msg.save()
    if problems:
      error_logger.log_error(
          'SMS delivery errors',
          '\n\n'.join(problems),
          extra_to=settings.ALERT_BAD_PHONE,
          always_new_error=True)

  def _send_first_and_return_next(self, send_these, front, verbose):
    send_next = []
    for send_me in send_these:
      phone = send_me.phone
      message = send_me.messages[0]
      if verbose:
        print('{} -> {}'.format(message[:30], phone))
      send_response = front.send_sms(phone, message)
      if len(send_me.messages) > 1:
        send_next.append(SMSManager.MessageList(
            send_me.guest_message, send_me.phone, send_me.messages[1:]))
      else:
        send_me.guest_message.handle_send_response(send_response)
    return send_next

  def notify_overdue_messages(
      self, clock=Clock(), error_logger=ErrorLogger(), verbose=False):
    overdues = self._way_overdue_for_sending(clock)
    if overdues:
      message = (
          'These messages didn\'t go out on time and must now be handled '
          'manually:\n\n{}').format(self._way_overdue_message(
              overdues, clock, verbose))
      error_logger.log_error(
          'Long overdue messages', message, always_new_error=True)
      self._overdue_dealt_with(overdues, clock)

  def _way_overdue_for_sending(self, clock):
    definitely_overdue = []
    hours_ago = timedelta(hours=settings.ALLOW_SMS_CATCH_UP_HOURS)
    for probable in self.filter(
        when_should__gte=clock.now() - timedelta(days=1),
        when_should__lte=clock.now() - hours_ago,
        when_did=None, why_did_not_send='').order_by('when_should'):
      # If the server went down for six hours or whatever, maybe we lucked
      # out and some of these messages that never got visited actually aren't
      # supposed to go out in the first place, so, no harm no foul.
      reason_why_not = probable.explain_why_do_not_send()
      if reason_why_not:
        probable.why_did_not_send = reason_why_not
        probable.save()
      else:
        definitely_overdue.append(probable)
    return definitely_overdue

  def _way_overdue_message(self, overdues, clock, verbose):
    entries = []
    for overdue in overdues:
      guest = overdue.reservation.guest
      message = (
          '{} {} {} Reservation id {}\n{}\n'
          'Should have sent {} hours ago').format(
              guest.phone,
              guest.full_name,
              overdue.reservation.listing.rental.nickname,
              overdue.reservation.pk,
              overdue.message,
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

  def _might_need_sending(self):
    # Checkin messages go out at 9am, and checkin is at 4pm. Therefore, if you
    # send a checkin message 7 hours late, you look stupid. Messages that are
    # more tardy than that need human handling. We get alerted of those by
    # ./manage.py alert_overdue_messages
    # Note there's an index on when_should so this stays fast.
    hours_ago = timedelta(hours=settings.ALLOW_SMS_CATCH_UP_HOURS)
    return self.filter(
        when_should__gte=now() - hours_ago, when_should__lte=now(),
        when_did=None).order_by('when_should')

  def _should_send(self, guest_message):
    return not guest_message.explain_why_do_not_send()


class SMS(models.Model):
  """ And here's an actual message that will be sent to a guest. """
  reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE)
  guesty_custom_field_id = models.CharField(max_length=100, help_text=(
      'If this guesty custom field is set to True for this reservation, turn '
      'this message off.'))
  special_purpose = models.CharField(
      max_length=30, null=True, blank=True, choices=SPECIAL_PURPOSES)
  # The index on when_should is so _might_need_sending stays fast.
  when_should = models.DateTimeField(db_index=True)
  when_did = models.DateTimeField(null=True, blank=True)
  green_light = models.BooleanField(help_text=(
      'Admins have the power to turn off individual SMS messages.'))
  message = models.TextField(help_text='The actual message that will be sent.')
  why_did_not_send = models.CharField(
      max_length=250, default='', help_text=(
          'This message came up to get sent, but it turned out we shouldn\'t '
          'have sent it. This is the reason why.'))
  created_at = models.DateTimeField(auto_now_add=True)
  sent_to_phone = models.CharField(
      max_length=50, null=True, blank=True, help_text=(
          'If we tried to send this message, what number did we try to '
          'send it to?'))
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

  objects = SMSManager()

  def get_delivery_error(self, front=Front()):
    if self.send_results:
      results = ast.literal_eval(self.send_results)
      return front.delivery_error(results['message_uid'])

  def __repr__(self):
    return '<SMS: {} "{}" {}>'.format(
        self.pk,
        self.message[:15],
        bool(self.when_did))

  def handle_send_response(self, send_response):
    results = send_response.json()
    self.send_results = str(results)
    self.sent_to_phone = self.reservation.guest.phone
    self.save()

  def guesty_custom_field_name(self):
    for field in GUESTY_MESSAGE_TOGGLE_CUSTOM_FIELDS:
      if field[0] == self.guesty_custom_field_id:
        return field[1]

  def explain_why_do_not_send(self):
    from id_verify.models import Submission
    if not self.reservation.confirmed():
      return 'The reservation is not confirmed.'
    if self.special_purpose == ID_VERIFICATION_REQUIRED:
      if self.reservation.id_verified:
        return 'ID_VERIFICATION_REQUIRED but the id is verified already.'
      elif Submission.objects.filter(reservation=self.reservation):
        return 'ID_VERIFICATION_REQUIRED but an id submission exists.'
    if self.special_purpose == MORNING_AFTER_ARRIVAL:
      if self.reservation.night_count == 1:
        return 'MORNING_AFTER_ARRIVAL and night_count == 1'
      id_etc = self._explain_why_id_paid_security_deposit_not_ok()
      if id_etc:
        return 'MORNING_AFTER_ARRIVAL {}'.format(id_etc)
    if self.special_purpose == PAYMENT_DEPOSIT_ID_RECEIVED:
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

  def _matches(self, template):
    return template._matches(self)
