import ast
from collections import namedtuple
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.dispatch import receiver
from django.utils.timezone import now

from errors.models import log_error, Notifier
from guest_messages.models.models_base import (
    Message, Template, MessageManager, TemplateManager)
from guest_messages.template_tags import TemplateTags, DELAY
from reservations.models import Reservation
from reservations.reservation_finder import ReservationFinder
from util.background import background
from util.clock import Clock
from util.signals import post_sync
from front.models import Front


@receiver(post_sync, sender=Reservation)
def post_sync(sender, instance, *args, **kwargs):
  if instance.confirmed() and instance.check_out > now():
    SMS.objects.create_prescheduled_for_reservation(instance)


class SMSTemplateManager(TemplateManager):
  def get_all_in_order(self):
    # I used to do something real fancy here with checkin comes before
    # checkout and so on. But then the forms couldn't juggle the ids
    # properly and everything got corrupted. So, just keep it simple
    # and annoying I guess.
    return self.all().order_by('pk')

  def triggered_message_for_reservation(self, triggering_event, reservation):
    template = self.get(
        triggering_event=triggering_event)
    return template.create_new_message(reservation)


class SMSTemplate(Template):
  message = models.TextField(help_text=(
      'The actual message that will be copied for every reservation.'))

  objects = SMSTemplateManager()

  def get_message_string(self, reservation):
    return TemplateTags().replace_template_tags_for_reservation(
        reservation, self.message)

  def create_new_message(self, reservation):
    message = SMS(
        message=self.get_message_string(reservation))
    return self.setup_new_message(reservation, message)

  def update_existing_message(self, exist):
    """ This is really more like, update the parts of the existing message
    that are particular to SMSs. MessageManager.update_existing_message
    has the shared stuff. """
    # We may have updated the wording of the messages.
    exist.message = self.get_message_string(exist.reservation)
    return self.setup_existing_message(exist)


class SMSManager(MessageManager):
  def get_plural_name(self):
    return 'SMSs'

  def send_test(self, post):
    # {template_id: template_id, to: to, reservation: reservation}
    template = SMSTemplate.objects.get(pk=post['template_id'])
    reservations = ReservationFinder().find(post['reservation'])
    if not reservations:
      return 'I couldn\'t find that reservation.'
    reservation = reservations[0]
    smss = self._sub_messages(template.get_message_string(reservation))
    self._do_send_test(smss, post['to'])
    return 'Sent'

  @background
  def _do_send_test(self, smss, to):
    for i, sms in enumerate(smss):
      if i > 0:
        Clock().sleep(30)
      response = Front().send_sms(to, sms, ok_to_do_it_in_dev=True)
      if not response.ok:
        raise Exception(
            'status code {} content {}'.format(
                response.status_code, response.content))

  def _sub_messages(self, message):
    smss = message.split('{' + DELAY + '}')
    return [m.strip() for m in smss]

  def get_prescheduled_templates(self):
    return SMSTemplate.objects.filter(pre_scheduled=True)

  # Just a little bookkeeping class here for the send function.
  SMSList = namedtuple(
      'SMSList', 'message phone smss')

  def send(
      self, sync=None, message_pk=None, front=Front(), clock=Clock(),
      verbose=False):
    """ This gets a bit complicated due to the {delay} tag! """
    send_these = []
    if message_pk:
      messages = self.filter(pk=message_pk)
    else:
      messages = self.need_sending(sync, clock, verbose)
    for guest_message in messages:
      guest_message.recaluclate_message()
      send_these.append(SMSManager.SMSList(
          guest_message, guest_message.get_send_to(),
          self._sub_messages(guest_message.message)))
    if verbose:
      print(
          '{} SMSs to send (not including delays)'.format(len(send_these)))
    sent_count = len(send_these)
    clock.start()
    took_too_long = 0
    while send_these:
      send_these = self._send_first_and_return_next(send_these, front, verbose)
      if send_these:
        time_it_took = clock.elapsed_seconds()
        sleep_for = 30 - time_it_took
        if sleep_for > 0:
          clock.sleep(sleep_for)
        else:
          took_too_long = time_it_took
        clock.start()
    if took_too_long:
      log_error('Sending {} SMSs took {} seconds'.format(
          sent_count, took_too_long), (
          'That\'s starting to get a little long. We ought to rework '
          'guest_messages/models.py#SMSManager.send to use threads '
          'or something.'))

  def _send_first_and_return_next(self, send_these, front, verbose):
    send_next = []
    for send_me in send_these:  # send_me is an SMSList, not an SMS
      phone = send_me.phone
      sms = send_me.smss[0]
      if verbose:
        print('SMS {} -> {}'.format(sms[:30], phone))
      send_response = front.send_sms(phone, sms)
      if len(send_me.smss) > 1:
        send_next.append(SMSManager.SMSList(
            send_me.message, send_me.phone, send_me.smss[1:]))
      else:
        send_me.message.send_results = str(send_response.json())
        send_me.message.when_did = now()
        send_me.message.sent_to = send_me.phone
        send_me.message.save()
    return send_next

  def verify_delivery(
      self, front=Front(), notifier=Notifier(), verbose=False):
    return self.verify_delivery_helper(
        front, notifier, verbose, 'SMS delivery errors')

  def need_to_verify_delivery(self):
    return self.filter(
        delivery_check_on=None, send_results__isnull=False,
        when_should__gt=now() - timedelta(days=7)).order_by('when_did')

  def verify_delivery_helper(
      self, get_delivery_error_arg, notifier, verbose, problem_email_subject):
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
            msg.reservation.admin_url(),
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
      notifier.notify(
          settings.ALERT_BAD_PHONE,
          problem_email_subject,
          '\n\n'.join(problems))


class SMS(Message):
  message = models.TextField(help_text='The actual message that will be sent.')
  template = models.ForeignKey(
      SMSTemplate, on_delete=models.CASCADE, help_text=(
          'What SMSTemplate was used to create this SMS?'))
  delivery_check_on = models.DateTimeField(null=True, blank=True)

  objects = SMSManager()

  def recaluclate_message(self):
    self.message = self.template.get_message_string(self.reservation)
    self.save()

  def get_send_to(self):
    return self.reservation.guest.phone

  def get_name_of_thing_you_send_to(self):
    return 'phone number'

  def describe_contents(self):
    return self.message

  def get_delivery_error(self, error_getter=None):
    error_getter = error_getter or Front()
    if self.send_results:
      return error_getter.delivery_error(ast.literal_eval(self.send_results))

  def get_pretty_type(self):
    return 'SMS'

  def __repr__(self):
    return '<SMS: {} "{}" {}>'.format(
        self.pk,
        self.message[:15],
        bool(self.when_did))
