"""
This is stuff that's specific to either guest SMSs or guest Emails, how to send
for instance.
"""
from abc import abstractmethod
import ast
from collections import namedtuple
from datetime import timedelta
import re

from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.timezone import now

from errors.models import log_error, ErrorLogger
from guest_messages.models_base import Message, Template, MessageManager
from reservations.models import Reservation
from util.channels import CHANNELS
from util.clock import Clock
from util.timezone import utc_dt_to_tz_dt
from front.models import Front


""" Custom template tags. See templates/admin/guest_message_templates.html
for how they're used. """
GUEST_FIRST_NAME = 'guest_first_name'
ADDRESS = 'address'
TAG_CLOSE = '/'
DELAY = 'delay'
CITY = 'city'
ID_VERIFY_LINK = 'id_verify_link'
GUEST_EMAIL = 'guest_email'
CHANNEL = 'channel'
CHECKOUT_TIME = 'checkout_time'


class ReservationSyncer(object):
  @abstractmethod
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


class SMSTemplate(Template):
  message = models.TextField(help_text=(
      'The actual message that will be copied for every reservation.'))

  objects = SMSTemplateManager()

  class Meta:
    ordering = ['pk']

  def message_for_reservation(self, reservation):
    message = self.message
    guest = reservation.guest
    message = self._simple_message_sub(
        GUEST_FIRST_NAME, guest.first_name or guest.full_name, message)
    message = self._simple_message_sub(
        ADDRESS, reservation.rental.airbnb_address_scrape, message)
    message = self._simple_message_sub(
        CITY, reservation.rental.city, message)
    message = self._simple_message_sub(
        ID_VERIFY_LINK, reservation.verify_id_url(), message)
    email = reservation.guest.email or reservation.anonymized_email
    message = self._simple_message_sub(GUEST_EMAIL, email, message)
    message = self._simple_message_sub(
        CHANNEL, reservation.channel or reservation.channel,
        message)
    message = self._simple_message_sub(
        CHECKOUT_TIME, reservation.check_out_time_string(), message)

    keep_tag = reservation.channel
    remove_tags = [c.lower() for c in CHANNELS]
    remove_me = keep_tag.lower()
    if remove_me not in remove_tags:
      raise Exception('{} not in {}'.format(remove_me, remove_tags))
    remove_tags.remove(remove_me)

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
        when_should=self.when_should(reservation),
        green_light=True,
        message=self.message_for_reservation(reservation),
        template=self)


@receiver(post_save, sender=Reservation)
def post_save(sender, instance, *args, **kwargs):
  SMS.objects.create_prescheduled_for_reservation(instance)


class SMSManager(MessageManager):
  def get_prescheduled_templates(self):
    return SMSTemplate.objects.filter(pre_scheduled=True)

  # Just a little bookkeeping class here for the send function.
  MessageList = namedtuple(
      'MessageList', 'guest_message phone messages')

  def get_for_reservation(self, reservation):
    return self.filter(reservation=reservation).order_by('when_should')

  def send(
      self, sync=None, message_pk=None, front=Front(), clock=Clock(),
      verbose=False):
    send_these = []
    sent_these = []
    if message_pk:
      messages = self.filter(pk=message_pk)
    else:
      messages = self.need_sending(sync, clock, verbose)
    for guest_message in messages:
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
        # At this point, sent_to is a new field and not necessarily
        # populated. Once this has been out for a few days this can be
        # simplified.
        phone = msg.sent_to
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
              guest.phone,
              guest.full_name,
              overdue.reservation.rental.nickname,
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

  def need_sending(self, sync, clock, verbose):
    return_me = []
    for message in self.filter(
        when_should__gte=clock.now() - timedelta(days=3),
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
          print('Dont send "{}" to {} because it\'s overdue.'.format(
              message.message[:30],
              message.reservation.guest.full_name))
      else:
        return_me.append(message)
    return return_me


class SMS(Message):
  message = models.TextField(help_text='The actual message that will be sent.')
  template = models.ForeignKey(
      SMSTemplate, on_delete=models.CASCADE, help_text=(
          'What SMSTemplate was used to create this SMS?'))

  objects = SMSManager()

  def get_template(self):
    return self.template

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
    self.sent_to = self.reservation.guest.phone
    self.save()
