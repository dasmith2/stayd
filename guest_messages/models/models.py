"""
This is stuff that's specific to either guest SMSs or guest Emails, how to send
for instance.
"""
import ast
from collections import namedtuple
from datetime import timedelta
import json

from django.conf import settings
from django.db import models
from django.dispatch import receiver
from django.utils.timezone import now
import mandrill

from errors.models import log_error, ErrorLogger
from guest_messages.mandrill import Emailer
from guest_messages.models.front_contact_updater import FrontContactUpdater
from guest_messages.models.models_base import (
    Message, Template, MessageManager, TemplateManager, BadContactInfo,
    FIRST_PAYMENT_DEPOSIT_ID_RECEIVED, CHECKIN_INSTRUCTIONS_EMAIL)
from guest_messages.template_tags import TemplateTags, DELAY
from reservations.models import Reservation
from reservations.reservation_finder import ReservationFinder
from util.background import background
from util.clock import Clock
from util.rm_old import RmOldManager
from util.signals import post_sync
from util.timezone import parse_dt, ts_to_utc_dt
from front.models import Front


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
    return TemplateTags().replace_template_tags_for_reservation(
        reservation, self.subject)

  def create_new_message(self, reservation):
    message = Email(subject=self.subject_for_reservation(reservation))
    return self.setup_new_message(reservation, message)

  def update_existing_message(self, exist):
    """ This is really more like, update the parts of the existing message
    that are particular to Emails. MessageManager.update_existing_message
    has the shared stuff. """
    exist.subject = self.subject_for_reservation(exist.reservation)
    return self.setup_existing_message(exist)


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


@receiver(post_sync, sender=Reservation)
def post_sync(sender, instance, *args, **kwargs):
  if instance.confirmed() and instance.check_out > now():
    SMS.objects.create_prescheduled_for_reservation(instance)
    Email.objects.create_prescheduled_for_reservation(instance)
    FrontContactUpdater().update_for_reservation_or_alert(instance)
  check_for_confirmation_email(instance)


@background
def check_for_confirmation_email(
    reservation, emailer=Emailer(), clock=Clock(), verbose=False):
  """ Just a reminder, @background functions can't be in a manager. """
  if Email.objects.should_send_confirmation(reservation, clock):
    Email.objects.send_confirmation(reservation, emailer, clock, verbose)


class EmailManager(MessageManager):
  def should_send_confirmation(self, reservation, clock):
    return not self.explain_why_do_not_send_confirmation(reservation, clock)

  def explain_why_do_not_send_confirmation(self, reservation, clock=Clock()):
    if reservation.rental.pk != settings.TEST_RENTAL and (
        clock.now() < parse_dt(settings.EMAIL_GOES_LIVE)):
      return 'Email isn\'t live yet.'
    if not reservation.confirmed():
      return 'This reservation isn\'t confirmed.'
    if reservation.check_out < clock.now():
      return 'Checkout happened already.'
    if not reservation.id_verified:
      return 'The ID isn\'t verified.'
    if reservation.we_assume_cc_risk():
      if not reservation.valid_payments_exist:
        return 'We haven\'t received a first payment yet.'
      if not reservation.security_deposit:
        return 'We haven\'t received a security deposit yet.'
    for existing in self.filter(
        reservation=reservation).select_related('template'):
      trigger = existing.template.triggering_event
      if trigger == FIRST_PAYMENT_DEPOSIT_ID_RECEIVED:
        return 'We sent the confirmation already.'
      guesty_field_id = existing.template.guesty_custom_field_id
      if guesty_field_id == CHECKIN_INSTRUCTIONS_EMAIL:
        if existing.when_should - timedelta(days=1) < clock.now():
          return 'Too close to the checkin instructions.'

  def send_confirmation(self, reservation, emailer, clock, verbose):
    template = EmailTemplate.objects.filter(
        triggering_event=FIRST_PAYMENT_DEPOSIT_ID_RECEIVED).first()
    if template:
      message = template.create_new_message(reservation)
      self.send(
          message_pk=message.pk, emailer=emailer, clock=clock, verbose=verbose)

  def get_plural_name(self):
    return 'emails'

  def send_test(self, post):
    # {template_id: template_id, to: to, reservation: reservation}
    template = EmailTemplate.objects.get(pk=post['template_id'])
    reservations = ReservationFinder().find(post['reservation'])
    if not reservations:
      return 'I couldn\'t find that reservation.'
    reservation = reservations[0]
    template_params = TemplateTags().get_template_params_for_reservation(
        reservation)
    subject = template.subject_for_reservation(reservation)
    try:
      Emailer().send_email(
          subject, post['to'], template_params,
          template.mailchimp_template)
    except mandrill.UnknownTemplateError:
      return (
          'Mandrill doesn\'t know about this template. Make sure you spelled '
          'it right, and make sure you clicked "Send to Mandrill" in '
          '<a href="https://us18.admin.mailchimp.com/templates/">Mailchimp'
          '</a>.')
    return 'Sent a test email to {}'.format(post['to'])

  def get_prescheduled_templates(self):
    return EmailTemplate.objects.filter(pre_scheduled=True)

  def send(
      self, sync=None, message_pk=None, emailer=Emailer(), clock=Clock(),
      verbose=False):
    if message_pk:
      messages = self.filter(pk=message_pk)
    else:
      messages = self.need_sending(sync, clock, verbose)

    for message in messages:
      email = message.get_send_to()
      subject = message.template.subject_for_reservation(message.reservation)
      if verbose:
        print('Emailing "{}" to {}'.format(subject, email))
      template_params = TemplateTags().get_template_params_for_reservation(
          message.reservation)

      message.when_did = clock.now()
      message.sent_to = message.get_send_to()
      message.subject = subject
      message.send_results = emailer.send_email(
          subject, email, template_params, message.template.mailchimp_template)
      message.save()
      # I got this down here just in case send_results is weird sometimes
      # and this becomes invalid.
      message.send_id = message.send_results[0]['_id']
      message.save()

  def verify_delivery(
      self, emailer=Emailer(), error_logger=ErrorLogger(), verbose=False):
    return self.verify_delivery_helper(
        emailer, error_logger, verbose, 'Email delivery errors')


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
    return 'Sending...'

  @background
  def _do_send_test(self, smss, to):
    for i, sms in enumerate(smss):
      if i > 0:
        Clock().sleep(30)
      Front().send_sms(to, sms, ok_to_do_it_in_dev=True)

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
      self, front=Front(), error_logger=ErrorLogger(), verbose=False):
    return self.verify_delivery_helper(
        front, error_logger, verbose, 'SMS delivery errors')

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
      error_logger.log_error(
          problem_email_subject,
          '\n\n'.join(problems),
          extra_to=settings.ALERT_BAD_PHONE,
          always_new_error=True)


# These will go into Email.delivery_error.
DELIVERY_PROBLEM_CHOICES = (
    ('hard_bounce', 'hard_bounce'),
    ('spam', 'spam'),
    ('unsub', 'unsub'),
    ('reject', 'reject'))


class Email(Message):
  subject = models.CharField(max_length=300, help_text=(
      'The actual subject line for this email.'))
  template = models.ForeignKey(
      EmailTemplate, null=True, blank=True, on_delete=models.CASCADE,
      help_text='What EmailTemplate was used to create this Email?')
  send_id = models.CharField(max_length=100, null=True, blank=True, help_text=(
      'When you send an email via Mandrill, it provides an _id variable. '
      'Then, webhooks will mention that id.'))
  opened = models.DateTimeField(null=True, blank=True, help_text=(
      'When was this email opened, if ever?'))

  objects = EmailManager()

  def get_send_to(self):
    guest_email = self.reservation.guest.email
    if guest_email:
      if not BadContactInfo.objects.filter(
          handle=guest_email, guest=self.reservation.guest).exists():
        return guest_email
    return self.reservation.anonymized_email

  def get_name_of_thing_you_send_to(self):
    return 'email'

  def describe_contents(self):
    return self.subject

  def get_pretty_type(self):
    return 'email'

  def explain_why_do_not_send(self):
    if self.reservation.rental.pk != settings.TEST_RENTAL:
      if self.when_should < parse_dt(settings.EMAIL_GOES_LIVE):
        return 'Email isn\'t live yet.'
    return super(Email, self).explain_why_do_not_send()

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


class RawMandrillEventManager(RmOldManager):
  def handle_webhook(
      self, request_POST, clock=Clock(), error_logger=ErrorLogger()):
    # Save the raw event first in case there's a problem processing it.
    # Then we can go back through and fix the problem.
    raw_event = self.create(json=json.dumps(request_POST))
    self.process_raw_event(raw_event, clock=clock, error_logger=error_logger)

  def process_raw_event(
      self, raw_event, clock=Clock(), error_logger=ErrorLogger()):
    for event in json.loads(json.loads(raw_event.json)['mandrill_events']):
      _id = event['_id']
      email = Email.objects.filter(send_id=_id).first()
      if not email:
        # This was probably a test email.
        pass
      else:
        if raw_event.email and raw_event.email != email:
          error_logger.log_error(
              'More than one email per mandrill webhook',
              'Might as well drop the email field on RawMandrillEvent.')
        raw_event.email = email
        expected_keys = [
            '_id', 'state', 'subject', 'email', 'tags', 'opens', 'clicks',
            'smtp_events', 'resends', '_version', 'sender', 'template', 'ts']
        msg = event['msg']
        for key in msg.keys():
          if key not in expected_keys:
            # I expect this is how I'll figure out how to populate
            # the Email.delivery_error field.
            error_logger.log_error(
                'Got unexpected key in mailchimp webhook', (
                    'The new key is "{}" on webhook {}. It\'s probably an '
                    'error we need to '
                    'handle. We probably need to add a log_error call here '
                    'that will inform somebody to reach out to the guest '
                    'and get a valid email, say.').format(key, raw_event.pk))
        opens = msg.get('opens', [])
        if opens:
          min_open = min([opn['ts'] for opn in opens])
          email.opened = ts_to_utc_dt(min_open)
          email.save()
    raw_event.handled_at = clock.now()
    raw_event.save()

  def rerun_webhooks(self, verbose=False):
    for raw_event in self.filter(handled_at=None):
      if verbose:
        print('Handled a raw mandrill event {}'.format(raw_event.pk))
      self.process_raw_event(raw_event)


class RawMandrillEvent(models.Model):
  """ Not unlike guesty.models.RawEvent """
  json = models.TextField(help_text='The raw json string from the request.')
  created_at = models.DateTimeField(auto_now_add=True, db_index=True)
  handled_at = models.DateTimeField(null=True, blank=True)
  email = models.ForeignKey(
      Email, blank=True, null=True, on_delete=models.CASCADE)

  objects = RawMandrillEventManager()
