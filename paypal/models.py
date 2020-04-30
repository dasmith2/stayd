from datetime import timedelta
import json
import time

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.dateparse import parse_datetime
from djmoney.models.fields import MoneyField
from djmoney.money import Money

from commands.models import background_command
from errors.models import ErrorLogger, Notifier
from paypal.api import API
from util import money
from util.html_status_codes import ServerError
from util.random_string import random_string
from util.timezone import now


@background_command
def check_status_background(
    api=None, nnow=None, error_logger=None, notifier=None):
  nnow = nnow or now()
  for payout in Payout.objects.need_status_check(nnow):
    payout.check_status(api=api, error_logger=error_logger, notifier=notifier)


SUCCESS = 'SUCCESS'
PENDING = 'PENDING'

INSUFFICIENT_FUNDS = 'INSUFFICIENT_FUNDS'
RECEIVER_UNREGISTERED = 'RECEIVER_UNREGISTERED'
RISK_DECLINE = 'RISK_DECLINE'


class PayoutManager(models.Manager):
  def need_status_check(self, nnow=None):
    nnow = nnow or now()
    return Payout.objects.filter(
        ~Q(payout_batch_id=''), transaction_status__in=['', PENDING],
        when_should__gte=nnow - timedelta(days=365))

  def send_test_dollar(self, email):
    payout = self.init_new_payout(
        pay_email=email,
        amount=Money(1, 'USD'),
        email_subject='email_subject. We can modify this.',
        note='note. We can modify this.',
        when_should=now())
    payout.send()
    return payout

  def init_new_payout(
      self, pay_email=None, amount=None, email_subject=None,
      note=None, when_should=None):
    return Payout.objects.create(
        pay_email=pay_email,
        amount=amount,
        email_subject=email_subject,
        note=note,
        when_should=when_should)


class Payout(models.Model):
  """ This table should contain records of every time we send somebody money
  through Paypal.

  Paypal keeps a distinction between a payout batch and a payout item. There's
  really no advantage to putting multiple items in the same batch. The fees are
  the same either way and it's not a performance issue. So we'll just do one
  item per batch because then we can have one less class/database table/join
  on our end.

  Paypal doesn't return data synchronously. You must make a separate call to
  get the status and such.

  See https://www.paypal.com/us/webapps/mpp/merchant-fees for fees. It's a flat
  paypal_fee of .25 per USD payout in the USA. That's not per batch, that's per
  item. """
  pay_email = models.CharField(
      blank=False, null=False, max_length=100, help_text=(
          'This email must be associated with a Paypal account.'))
  amount = MoneyField(max_digits=10, decimal_places=2, default_currency='XYZ')
  # Paypal throws an error if you try to make this gt 255 chars
  email_subject = models.CharField(
      help_text='We can set this to whatever we want.', max_length=255)
  note = models.TextField(help_text='We can set this to whatever we want.')
  when_should = models.DateTimeField(help_text='When should they get paid')

  when_did = models.DateTimeField(
      help_text='When did they get paid', null=True, db_index=True)

  # Default currency is useless. Always specify currency.
  paypal_fee = MoneyField(
      max_digits=10, decimal_places=2, default_currency='XYZ', blank=True,
      null=True, help_text=(
          'The paypal_fee paypal charged to send this payout, '
          'typically $.25 USD.'))
  payout_batch_id = models.CharField(
      max_length=30, default='', help_text=(
          'Set by Paypal. We only put one payout_item in each batch, '
          'which explains some of the redundancy.'))
  sender_batch_id = models.CharField(
      max_length=30, blank=True, null=True,
      help_text='An id for communicating with external people.')
  payout_item_id = models.CharField(max_length=30, default='', help_text=(
      'Set by Paypal. We always do one payout item in one batch.'))
  transaction_id = models.CharField(
      max_length=30, default='', help_text=(
          'Set by Paypal on the item level. This is maybe important?'))
  # For a complete list of possible statuses see
  # https://developer.paypal.com/docs/api/payments.payouts-batch/v1/#definition-payout_item_response
  transaction_status = models.CharField(
      max_length=30, blank=True, null=False, default='', help_text=(
          'Set by Paypal on the item level. This is important.'))
  batch_status = models.CharField(default='', max_length=30, help_text=(
      'Set by Paypal on the batch level. This can be SUCCESS, '
      'PROCESSING, or PENDING (that I know of).'))
  error_name = models.TextField(default='', help_text=(
      'Set on the item level. This is important-ish, but error_message '
      'is more helpful.'))
  error_message = models.TextField(default='', help_text=(
      'Set on the item level. This is important.'))

  objects = PayoutManager()

  def status(self):
    return self.error_name or self.transaction_status or self.batch_status

  def is_sent(self):
    return bool(self.batch_status)

  def success(self):
    return self.batch_status == SUCCESS

  def pending(self):
    return self.status() == PENDING

  def payout_status(self):
    if self.batch_status:
      return self.batch_status
    return 'Unsent'

  def get_send_data(self):
    # sender_batch_id and sender_item_id just need to be unique. Because we
    # only put one item in every batch it's ok to use sender_batch_id for both.
    # Because tests run on fresh databases, using self.pk alone is
    # insufficient.
    return {
        'sender_batch_header': {
            'sender_batch_id': self.sender_batch_id,
            'email_subject': self.email_subject
        },
        'items': [{
            'recipient_type': 'EMAIL',
            'amount': {
                'value': money.number_only_format(self.amount),
                'currency': str(self.amount.currency)
            },
            'note': self.note,
            'sender_item_id': self.sender_batch_id,
            'receiver': self.pay_email}]}

  def send(self, api=None, error_logger=None):
    api = api or API()
    if not self.sender_batch_id:
      raise Exception(
          'I can\'t send a payment without a sender_batch_id. See '
          'compute_sender_batch_id')

    # OK, I don't have a great circle back around mechanism here. But also
    # server errors at this point are fairly rare. So, for now let's just do a
    # simple retry and see if that does the trick.
    got_server_error = None
    data = None
    attempts = 0
    while not data and attempts < 3:
      try:
        # Did you get an email error that said the following line raised a
        # ServerError, and you're confused because we catch that server error?
        # Just look a little closer. If the error happens multiple times I
        # re-raise the exception later, and that exception includes this line.
        data = api.send_payout(self.get_send_data())
        got_server_error = None
      except ServerError as ex:
        data = None  # Just for clarity.
        got_server_error = ex
        time.sleep(1)
      attempts += 1
    if got_server_error:
      raise got_server_error

    if 'batch_header' in data:
      batch_header = data['batch_header']

      self.batch_status = batch_header['batch_status']
      self.payout_batch_id = batch_header['payout_batch_id']
      self.save()
    else:
      self.error_name = data['name']
      self.error_message = 'Sending {} caused {}'.format(
          json.dumps(self.get_send_data(), indent=2),
          json.dumps(data, indent=2))
      self.save()
      self._log_if_error('Paypal send error', error_logger=error_logger)

  def check_status(self, api=None, error_logger=None, notifier=None):
    # If there's a problem at the time of sending, INSUFFICIENT_FUNDS say, you
    # don't get a batch_id back so there's no status to check.
    if not self.payout_batch_id:
      return self
    api = api or API()

    data = api.get_status(self.payout_batch_id)
    batch_header = data['batch_header']
    self.batch_status = batch_header['batch_status']
    fees = batch_header['fees']
    self.paypal_fee = Money(float(fees['value']), fees['currency'])
    item = data['items'][0]
    # It's called errors but it's not a list, just a single error.
    if 'errors' in item:
      error = item['errors']
      self.error_name = error['name']
      self.error_message = error['message']
    else:
      self.error_name = ''
      self.error_message = ''
    self.payout_item_id = item['payout_item_id']
    self.transaction_status = item['transaction_status']
    if 'transaction_id' in item:
      # a.k.a. if self.transaction_status not in [PENDING, 'FAILED']:
      self.transaction_id = item['transaction_id']
      self.when_did = parse_datetime(item['time_processed'])
    self.save()
    self._log_if_error('Paypal status error', error_logger, notifier)
    return self

  def _log_if_error(self, title, error_logger=None, notifier=None):
    error_logger = error_logger or ErrorLogger()
    notifier = notifier or Notifier()
    if self.error_name:
      if self._insufficient_funds():
        # Insufficient funds is in the regular flow of things and ought to be
        # handled with user interfaces and such.
        pass
      elif self._receiver_unregistered():
        message = (
            'Could somebody please contact {} and encourage them to sign up '
            'for Paypal so we can pay them?').format(self.pay_email)
        notifier.notify(
            [settings.ALERT_SERVICE_PROVIDER_NEEDS_PAYPAL],
            '{} isn\'t signed up for Paypal'.format(self.pay_email),
            message)
      elif self._risk_decline():
        message = (
            'We received a RISK_DECLINED error when we tried to pay them. '
            'The last time this happened, it was because the service provider '
            'failed to confirm her email with Paypal. Ask this service '
            'provider to make sure they\'ve completed all the sign up steps, '
            'especially confirming their email with Paypal, then retry this '
            'payment on '
            'https://keys.hihoward.com/work/pay_service_providers/.').format(
                self.pay_email)
        subject = 'Paypal signup probably incomplete: {}'.format(
            self.pay_email)
        notifier.notify(
            [settings.ALERT_SERVICE_PROVIDER_NEEDS_PAYPAL], subject, message)
      else:
        message = 'paypal.Payout pk {}'.format(self.pk)
        if self.error_message:
          message += '\n\n{}'.format(self.error_message)
        error_logger.log_error(
            '{}: {}'.format(title, self.error_name),
            message, always_new_error=True)

  def _insufficient_funds(self):
    """ We didn't have enough money in our Paypal account to pay them. """
    return self.error_name == INSUFFICIENT_FUNDS

  def _receiver_unregistered(self):
    """ We tried to pay somebody without a paypal account. """
    return self.error_name == RECEIVER_UNREGISTERED

  def _risk_decline(self):
    """ Still not sure how to resolve this one. """
    return self.error_name == RISK_DECLINE

  def paid_out_already(self):
    return bool(self.when_did)

  def compute_sender_batch_id(self):
    """ This should get called once for every payout. It's in a post_save at
    the bottom of this file. """
    if self.sender_batch_id:
      return self.sender_batch_id
    if not self.pk:
      raise Exception('I can\'t compute an id until this object has a pk.')
    id_so_far = '{}_'.format(self.pk)
    if len(id_so_far) < 7:
      id_so_far += random_string(7 - len(id_so_far))
    self.sender_batch_id = id_so_far
    self.save()
    return id_so_far

  def __repr__(self):
    return '<Payout {}: {} {} {} {}>'.format(
        self.pk,
        self.amount,
        self.pay_email,
        self.when_should.date(),
        self.status())


@receiver(post_save, sender=Payout)
def payout_post_save(sender, instance, *args, **kwargs):
  instance.compute_sender_batch_id()
