"""
Guest messages. For each purpose, there are configurable settings such as,
"What is the actual wording of the message?" There are also non-configurable
settings such as the hardcoded purpose. A hardcoded purpose lets us write
"""
from collections import namedtuple
from datetime import timedelta, time
import re

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from rentals.models import Airvatar
from reservations.models import Reservation
from util.channels import AIRBNB, BOOKINGCOM
from util.clock import Clock
from util.error_reporting import resolve_me
from util.front import Front



TELL_US_ARRIVAL = 'tell_us_arrival'
SPECIAL_PURPOSES = (
    (TELL_US_ARRIVAL, 'They haven\'t told us an arrival time yet.'),)


DAYS = 'days'
HOURS = 'hours'
DAYS_OR_HOURS = ((DAYS, DAYS), (HOURS, HOURS))

BEFORE = 'before'
AFTER = 'after'
BEFORE_OR_AFTER = ((BEFORE, BEFORE), (AFTER, AFTER))

CHECKIN = 'checkin'
CHECKOUT = 'checkout'
CHECKIN_OR_CHECKOUT = ((CHECKIN, CHECKIN), (CHECKOUT, CHECKOUT))

GUEST_FIRST_NAME = 'guest_first_name'
ADDRESS = 'address'
IF_WE_REVIEW_THEM = 'if_we_review_them'
IF_WE_REVIEW_THEM_OPEN = IF_WE_REVIEW_THEM
IF_WE_REVIEW_THEM_CLOSE = '/'
DELAY = 'delay'

TAGS = (
    (GUEST_FIRST_NAME, ''),
    (ADDRESS, 'The address of the reservation'),
    (IF_WE_REVIEW_THEM,
        '{if_we_review_them}We\'ll be sure to leave a 5 star review!{/}'),
    (DELAY, (
        'Send what we got so far, wait about 30 seconds, '
        'and then keep sending.')))


class TemplateManager(models.Manager):
  def get_all_in_order(self):
    return sorted(self.all(), key=lambda t: t.sort_key())


class Template(models.Model):
  """ Here's where we group the configurable settings for a template. """
  guesty_custom_field_name = models.CharField(
      max_length=100, unique=True, help_text=(
          'If the boolean guesty custom field for a reservation with this '
          'name is set to False, then the corresponding message should '
          'turn off the green light.'))
  special_purpose = models.CharField(
      max_length=20, null=True, blank=True, choices=SPECIAL_PURPOSES)
  offset = models.PositiveIntegerField(help_text=(
      'How many days or hours from the checkin or checkout should these '
      'messages be sent?'))
  days_or_hours = models.CharField(
      max_length=5, choices=DAYS_OR_HOURS, help_text=(
          'Does offset refer to days or hours?'))
  before_or_after = models.CharField(
      max_length=6, choices=BEFORE_OR_AFTER, help_text=(
          'Should these be sent before or after?'))
  checkin_or_checkout = models.CharField(
      max_length=8, choices=CHECKIN_OR_CHECKOUT, help_text=(
          'Do offset_hours and before_or_after refer to checkin or checkout?'))
  message = models.TextField(help_text=(
      'The actual message that will be copied for every reservation.'))

  objects = TemplateManager()

  def sort_key(self):
    if not self.pk:
      return (2, 0)
    offset_hours = self.offset
    if self.days_or_hours == DAYS:
      offset_hours *= 24
    if self.before_or_after == BEFORE:
      offset_hours *= -1
    return (
        0 if self.checkin_or_checkout == CHECKIN else 1,
        offset_hours)

  def _matches(self, guest_message):
    message_field = guest_message.guesty_custom_field_name
    return self.guesty_custom_field_name == message_field

  def when_should_for_reservation(self, reservation):
    if self.days_or_hours == DAYS:
      delta = timedelta(days=self.offset)
    else:
      delta = timedelta(hours=self.offset)
    if self.before_or_after == BEFORE:
      delta = -delta
    if self.checkin_or_checkout == CHECKIN:
      return reservation.check_in + delta
    return reservation.check_out + delta

  def _simple_message_sub(self, tag_name, replacement, message):
    return re.sub('{' + tag_name + '}', replacement, message)

  def message_for_reservation(self, reservation):
    message = self.message
    guest = reservation.guest
    message = self._simple_message_sub(
        GUEST_FIRST_NAME, guest.first_name or guest.full_name, message)
    message = self._simple_message_sub(
        ADDRESS, reservation.listing.rental.airbnb_address_scrape, message)
    if reservation.listing.channel == AIRBNB:
      message = self._simple_message_sub(
          IF_WE_REVIEW_THEM_OPEN, '', message)
      message = self._simple_message_sub(
          IF_WE_REVIEW_THEM_CLOSE, '', message)
    else:
      o = IF_WE_REVIEW_THEM_OPEN
      c = IF_WE_REVIEW_THEM_CLOSE
      message = re.sub(r'{' + o + '}.*{' + c + '}', '', message)
    return message

  def create_for_reservation(self, reservation):
    return Message.objects.create(
        reservation=reservation,
        guesty_custom_field_name=self.guesty_custom_field_name,
        special_purpose=self.special_purpose,
        when_should=self.when_should_for_reservation(reservation),
        green_light=True,
        message=self.message_for_reservation(reservation))


class MessageManager(models.Manager):
  def get_for_reservation(self, reservation):
    return self.filter(reservation=reservation).order_by('when_should')

  def create_for_reservation(self, reservation):
    existing = self.get_for_reservation(reservation)
    templates = Template.objects.all()
    for exist in existing:
      if not [t for t in templates if t._matches(exist)]:
        exist.delete()
    to_return = []
    for template in templates:
      exists = [e for e in existing if e._matches(template)]
      if exists:
        to_return.append(exists[0])
      else:
        to_return.append(template.create_for_reservation(reservation))

  def _might_need_sending(self):
    now = timezone.now()
    # Don't bother to send anything that's more than a day overdue because
    # a) if we mess up once by not sending a message, sending it at a totally
    # innapropriate time is no kind of solution, and b) there's an index on
    # when_should so if we timebox our search on that field, this will stay
    # fast.
    return self.filter(
        when_should__gte=now - timedelta(days=1), when_should__lte=now,
        when_did=None).order_by('when_should')

  def _get_front_channel(self, guest_message):
    airvatar = guest_message.reservation.listing.rental.airvatar
    if not airvatar:
      error_message = (
          'I can\'t send an SMS for reservation {} because I can\'t find '
          'an Airvatar for rental {}.'.format(
              guest_message.reservation.channel_reservation_id,
              guest_message.reservation.listing.rental.airbnb_address_scrape))
      resolve_me('Missing Airvatar', error_message)
    elif not airvatar.front_channel:
      airvatar_edit_url = settings.THIS_SERVERS_BASE_URL + reverse(
          'admin:listings_airvatar_change', args=[airvatar.pk])
      resolve_me('Missing front_channel on Airvatar', (
          'Airvatar {} needs a front_channel in order for me to send this '
          'SMS here.'.format(airvatar_edit_url)))
    else:
      return airvatar.front_channel

  def send(self, front=Front(), clock=Clock()):
    MessageList = namedtuple('MessageList', 'phone front_channel messages')
    send_these = []
    for guest_message in self._might_need_sending():
      # if guest_message.special_purpose == TELL_US_ARRIVAL and
      #     ?they told us their arrival already?:
      #   continue
      front_channel = self._get_front_channel(guest_message)
      if front_channel:
        phone = guest_message.reservation.guest.phone
        messages = guest_message.message.split('{' + DELAY + '}')
        send_these.append(MessageList(phone, front_channel, messages))
    sent_count = len(send_these)
    clock.start()
    took_too_long = 0
    while send_these:
      send_next = []
      for send_me in send_these:
        front.send_sms(
            send_me.phone, send_me.front_channel, send_me.messages[0])
        if len(send_me.messages) > 1:
          send_next.append(MessageList(
              send_me.phone, send_me.front_channel, send_me.messages[1:]))
      send_these = send_next
      if send_these:
        time_it_took = clock.elapsed_seconds()
        sleep_for = 30 - time_it_took
        if sleep_for > 0:
          clock.sleep(sleep_for)
        else:
          took_too_long = time_it_took
        clock.start()
    if took_too_long:
      resolve_me('Sending {} SMSs took {} seconds'.format(
          sent_count, took_too_long), (
          'That\'s starting to get a little long. We ought to rework '
          'guest_messages/models.py#MessageManager.send to use threads '
          'or something.'))


class Message(models.Model):
  """ And here's an actual message that will be sent to a guest. """
  reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE)
  guesty_custom_field_name = models.CharField(max_length=100)
  special_purpose = models.CharField(
      max_length=20, null=True, blank=True, choices=SPECIAL_PURPOSES)
  # The index on when_should is so _might_need_sending stays fast.
  when_should = models.DateTimeField(db_index=True)
  when_did = models.DateTimeField(null=True, blank=True)
  green_light = models.BooleanField()
  message = models.TextField(help_text='The actual message that will be sent.')

  objects = MessageManager()

  def _matches(self, template):
    return template._matches(self)
