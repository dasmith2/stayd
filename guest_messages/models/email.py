from datetime import timedelta
import json
from json import JSONDecodeError

from django.conf import settings
from django.db import models
from django.dispatch import receiver
from util.timezone import now
import mandrill

from errors.models import ErrorLogger
from guest_messages.mandrill import Emailer
from guest_messages.models.message import (
    Message, Template, MessageManager, TemplateManager, BadContactInfo,
    FIRST_PAYMENT_DEPOSIT_ID_BG_CHECK_RECEIVED)
from guest_messages.template_tags import TemplateTags
from guesty.custom_field_ids import CHECKIN_INSTRUCTIONS_EMAIL
from reservations.models import Reservation
from reservations.reservation_finder import ReservationFinder
from util.background import background
from util.clock import Clock
from util.rm_old import RmOldManager
from util.signals import post_sync
from util.timezone import parse_dt, ts_to_utc_dt


@receiver(post_sync, sender=Reservation)
def post_sync(sender, instance, *args, **kwargs):
  if instance.confirmed() and instance.check_out > now():
    Email.objects.create_prescheduled_for_reservation(instance)
  check_for_confirmation_email(instance)


class EmailTemplateManager(TemplateManager):
  pass


def checkin_instructions_template():
  return EmailTemplate.objects.filter(
      guesty_custom_field_id=CHECKIN_INSTRUCTIONS_EMAIL).first()


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


@background
def check_for_confirmation_email(
    reservation, emailer=Emailer(), clock=Clock(), verbose=False):
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
    if not reservation.background_check_valid():
      return 'The background check is non-valid'
    for existing in self.filter(
        reservation=reservation).select_related('template'):
      trigger = existing.template.triggering_event
      if trigger == FIRST_PAYMENT_DEPOSIT_ID_BG_CHECK_RECEIVED:
        return 'We sent the confirmation already.'
      guesty_field_id = existing.template.guesty_custom_field_id
      if guesty_field_id == CHECKIN_INSTRUCTIONS_EMAIL:
        if existing.when_should - timedelta(days=1) < clock.now():
          return 'Too close to the checkin instructions.'

  def get_checkin_instructions(self, reservation):
    return self.filter(
        template__guesty_custom_field_id=CHECKIN_INSTRUCTIONS_EMAIL,
        reservation=reservation)

  def send_confirmation(self, reservation, emailer, clock, verbose):
    template = EmailTemplate.objects.filter(
        triggering_event=FIRST_PAYMENT_DEPOSIT_ID_BG_CHECK_RECEIVED).first()
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
          template.mailchimp_template, ok_to_do_it_in_dev=True)
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
      self, message_pk=None, emailer=None, clock=None, verbose=False):
    emailer = emailer or Emailer()
    clock = clock or Clock()
    if message_pk:
      messages = self.filter(pk=message_pk)
    else:
      messages = self.need_sending(clock, verbose)

    for message in messages:
      if message.when_did:
        continue
      email = message.get_send_to()
      subject = message.template.subject_for_reservation(message.reservation)
      if verbose:
        print('Emailing "{}" to {}'.format(subject, email))
      template_params = TemplateTags().get_template_params_for_reservation(
          message.reservation)

      # Yeah... unfortunately the mandrill library makes the assumption that
      # all requests will be valid and always calls, like,
      # mandrill_response.json(). This causes JSONDecodeErrors when there are
      # 500 server errors or whatever. Let's just let it try again in an hour.
      try:
        message.send_results = emailer.send_email(
            subject, email, template_params,
            message.template.mailchimp_template)
        message.when_did = clock.now()
      except (JSONDecodeError, ConnectionError):
        message.send_results = 'Unknown Mandrill error'
      message.send_attempts += 1
      message.sent_to = message.get_send_to()
      message.subject = subject
      message.save()
      # I got this down here just in case send_results is weird sometimes and
      # this becomes invalid. send_results has an id in it only in the case of
      # a successful send.
      if message.when_did:
        message.send_id = message.send_results[0]['_id']
        message.save()


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
        msg_data = event['msg']
        if msg_data.get('state', None) == 'rejected':
          email.delivery_error = 'This email was rejected by the recipient'
          email.save()
        unexpected_keys = [
            key for key in msg_data.keys() if not self._is_expected_key(key)]
        if unexpected_keys:
          # I expect this is how I'll figure out how to populate the
          # Email.delivery_error field.
          error_logger.log_error(
              'Got unexpected key(s) in mailchimp webhook', (
                  'The new key(s) is/are "{}" on webhook {}. It\'s probably '
                  'an error we need to '
                  'handle. We probably need to add a log_error call here '
                  'that will inform somebody to reach out to the guest '
                  'and get a valid email, say.\n\n{}').format(
                      unexpected_keys, raw_event.pk, msg_data))
        opens = msg_data.get('opens', [])
        if opens:
          min_open = min([opn['ts'] for opn in opens])
          email.opened = ts_to_utc_dt(min_open)
          email.save()
    raw_event.handled_at = clock.now()
    raw_event.save()

  def _is_expected_key(self, key):
    good_keys = [
        '_id', 'state', 'subject', 'email', 'tags', 'opens', 'clicks',
        'smtp_events', 'resends', '_version', 'sender', 'template', 'ts',
        'subaccount', 'reject']
    # See WEIRD_SOFT_BOUNCE_EVENT
    weird_keys = ['bgtools_code', 'diag', 'bounce_description']
    return key in good_keys + weird_keys

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

  objects = RawMandrillEventManager()


class Email(Message):
  subject = models.CharField(max_length=300, help_text=(
      'The actual subject line for this email.'))
  template = models.ForeignKey(
      EmailTemplate, null=True, blank=True, on_delete=models.PROTECT,
      help_text='What EmailTemplate was used to create this Email?')
  send_id = models.CharField(max_length=100, null=True, blank=True, help_text=(
      'When you send an email via Mandrill, it provides an _id variable. '
      'Then, webhooks will mention that id.'))
  opened = models.DateTimeField(null=True, blank=True, help_text=(
      'When was this email opened, if ever?'))
  send_attempts = models.PositiveIntegerField(default=0, help_text=(
      'The mandrill library swallows errors, so Im using this field to see if '
      'any errors we do get are message specific.'))
  send_to_override = models.CharField(default='', max_length=200, help_text=(
      'Sometimes the guest will want checkin instructions sent to a '
      'sepcific email they tell a VA or something'))

  objects = EmailManager()

  def get_send_to(self):
    if self.send_to_override:
      return self.send_to_override
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

  def get_template(self):
    return self.template

  def explain_why_do_not_send(self):
    if self.reservation.rental.pk != settings.TEST_RENTAL:
      if self.when_should < parse_dt(settings.EMAIL_GOES_LIVE):
        return 'Email isn\'t live yet.'
    return super().explain_why_do_not_send()

  def __repr__(self):
    return '<Email: {} "{}" {}>'.format(
        self.pk,
        self.subject[:15],
        bool(self.when_did))
