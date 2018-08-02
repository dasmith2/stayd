"""
This is stuff that's specific to either guest SMSs or guest Emails, how to send
for instance.
"""
from abc import abstractmethod
import ast
from collections import namedtuple

from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.timezone import now

from errors.models import log_error, ErrorLogger
from guest_messages.mandrill import Emailer
from guest_messages.models_base import (
    Message, Template, MessageManager, TemplateManager, DELAY)
from reservations.models import Reservation
from reservations.reservation_finder import ReservationFinder
from util.clock import Clock
from front.models import Front


class ReservationSyncer(object):
  @abstractmethod
  def sync_stayd_reservation(self, reservation):
    raise NotImplementedError('sync_stayd_reservation')


class SMSTemplateManager(TemplateManager):
  def get_all_in_order(self):
    # I used to do something real fancy here with checkin comes before
    # checkout and so on. But then the forms couldn't juggle the ids
    # properly and everything got corrupted. So, just keep it simple
    # and annoying I guess.
    return self.all().order_by('pk')

  def create_new_message(self, guesty_custom_field_id, reservation):
    template = SMSTemplate.objects.get(
        guesty_custom_field_id=guesty_custom_field_id)
    return template.create_new_message(reservation)


class EmailTemplateManager(TemplateManager):
  pass


class EmailTemplate(Template):
  mailchimp_template = models.CharField(max_length=300, help_text=(
      'The literal name of the mailchimp template from '
      'https://us18.admin.mailchimp.com/templates/'))
  subject = models.CharField(max_length=300, default='', help_text=(
      'The subject of the email'))

  objects = EmailTemplateManager()

  def subject_for_reservation(self, reservation):
    return self.replace_template_tags_for_reservation(
        reservation, self.subject)

  def create_new_message(self, reservation):
    message = Email(
        subject=self.subject_for_reservation(reservation),
        sent_to=reservation.guest.email)
    return self.setup_new_message(reservation, message)

  def update_existing_message(self, exist):
    """ This is really more like, update the parts of the existing message
    that are particular to Emails. MessageManager.update_existing_message
    has the shared stuff. """
    exist.subject = self.subject_for_reservation(exist.reservation)
    exist.sent_to = exist.reservation.guest.email
    return self.setup_existing_message(exist)


class SMSTemplate(Template):
  message = models.TextField(help_text=(
      'The actual message that will be copied for every reservation.'))

  objects = SMSTemplateManager()

  def get_message_string(self, reservation):
    return self.replace_template_tags_for_reservation(
        reservation, self.message)

  def create_new_message(self, reservation):
    message = SMS(
        message=self.get_message_string(reservation),
        sent_to=reservation.guest.phone)
    return self.setup_new_message(reservation, message)

  def update_existing_message(self, exist):
    """ This is really more like, update the parts of the existing message
    that are particular to SMSs. MessageManager.update_existing_message
    has the shared stuff. """
    # We may have updated the wording of the messages.
    exist.message = self.get_message_string(exist.reservation)
    exist.sent_to = exist.reservation.guest.phone
    return self.setup_existing_message(exist)


@receiver(post_save, sender=Reservation)
def post_save(sender, instance, *args, **kwargs):
  if instance.confirmed():
    SMS.objects.create_prescheduled_for_reservation(instance)
    Email.objects.create_prescheduled_for_reservation(instance)


class EmailManager(MessageManager):
  def get_plural_name(self):
    return 'emails'

  def send_test(self, post):
    # {template_id: template_id, to: to, reservation: reservation}
    template = EmailTemplate.objects.get(pk=post['template_id'])
    reservations = ReservationFinder().find(post['reservation'])
    if not reservations:
      return 'I couldn\'t find that reservation.'
    template_params = self.get_template_params_for_reservation(reservations[0])
    Emailer().send_email(
        template.subject, post['to'], template_params,
        template.mailchimp_template)
    return 'Sent a test email to {}'.format(post['to'])

  def get_prescheduled_templates(self):
    return EmailTemplate.objects.filter(pre_scheduled=True)

  def get_template_params_for_reservation(self, reservation):
    first_name = reservation.guest.first_name or reservation.guest.full_name
    return {'guest_first_name': first_name}

  def send(
      self, sync=None, message_pk=None, emailer=Emailer(), clock=Clock(),
      verbose=False):
    if message_pk:
      messages = self.filter(pk=message_pk)
    else:
      messages = self.need_sending(sync, clock, verbose)

    for message in messages:
      email = message.reservation.guest.email
      subject = message.template.subject_for_reservation(message.reservation)
      template_params = Email.objects.get_template_params_for_reservation(
          message.reservation)

      message.sent_to = email
      message.subject = subject
      message.when_did = clock.now()
      message.send_results = emailer.send_email(
          subject, email, template_params, message.template.mailchimp_template)
      message.save()

  def verify_delivery(
      self, emailer=Emailer(), error_logger=ErrorLogger(), verbose=False):
    return self.verify_delivery_helper(
        emailer, error_logger, verbose, 'Email delivery errors')


class SMSManager(MessageManager):
  def get_plural_name(self):
    return 'SMSs'

  def send_test(self, post):
    return 'Not implemented yet.'

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
    sent_these = []
    if message_pk:
      messages = self.filter(pk=message_pk)
    else:
      messages = self.need_sending(sync, clock, verbose)
    for message in messages:
      phone = message.reservation.guest.phone
      smss = message.message.split('{' + DELAY + '}')
      smss = [m.strip() for m in smss]
      send_these.append(
          SMSManager.SMSList(message, phone, smss))
      sent_these.append(message)
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
      guest_message.sent_to = guest_message.reservation.guest.phone
      guest_message.save()
    if took_too_long:
      log_error('Sending {} SMSs took {} seconds'.format(
          sent_count, took_too_long), (
          'That\'s starting to get a little long. We ought to rework '
          'guest_messages/models.py#SMSManager.send to use threads '
          'or something.'))

  def _send_first_and_return_next(self, send_these, front, verbose):
    send_next = []
    for send_me in send_these:
      phone = send_me.phone
      sms = send_me.smss[0]
      if verbose:
        print('{} -> {}'.format(sms[:30], phone))
      send_response = front.send_sms(phone, sms)
      if len(send_me.smss) > 1:
        send_next.append(SMSManager.SMSList(
            send_me.message, send_me.phone, send_me.smss[1:]))
      else:
        send_me.message.send_results = str(send_response.json())
        send_me.message.save()
    return send_next

  def verify_delivery(
      self, front=Front(), error_logger=ErrorLogger(), verbose=False):
    return self.verify_delivery_helper(
        front, error_logger, verbose, 'SMS delivery errors')


class Email(Message):
  subject = models.CharField(max_length=300, help_text=(
      'The actual subject line for this email.'))
  template = models.ForeignKey(
      EmailTemplate, null=True, blank=True, on_delete=models.CASCADE,
      help_text='What EmailTemplate was used to create this Email?')

  objects = EmailManager()

  def get_send_to(self):
    return self.reservation.guest.email

  def get_name_of_thing_you_send_to(self):
    return 'email'

  def describe_contents(self):
    return self.subject

  def get_delivery_error(self, error_getter=None):
    error_getter = error_getter or Emailer()
    if self.send_results:
      results = ast.literal_eval(self.send_results)
      return error_getter.delivery_error(results['_id'])

  def __repr__(self):
    return '<Email: {} "{}" {}>'.format(
        self.pk,
        self.subject[:15],
        bool(self.when_did))


class SMS(Message):
  message = models.TextField(help_text='The actual message that will be sent.')
  template = models.ForeignKey(
      SMSTemplate, on_delete=models.CASCADE, help_text=(
          'What SMSTemplate was used to create this SMS?'))

  objects = SMSManager()

  def get_send_to(self):
    return self.reservation.guest.phone

  def get_name_of_thing_you_send_to(self):
    return 'phone number'

  def describe_contents(self):
    return self.message

  def get_delivery_error(self, error_getter=None):
    error_getter = error_getter or Front()
    if self.send_results:
      results = ast.literal_eval(self.send_results)
      return error_getter.delivery_error(results['message_uid'])

  def __repr__(self):
    return '<SMS: {} "{}" {}>'.format(
        self.pk,
        self.message[:15],
        bool(self.when_did))
