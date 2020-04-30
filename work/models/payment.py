from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from djmoney.models.fields import MoneyField
from djmoney.money import Money

from errors.models import log_error, notify
from paypal.models import (
    Payout, INSUFFICIENT_FUNDS, RECEIVER_UNREGISTERED, RISK_DECLINE)
from work.models.work import Worker, Work
from work.models.worker import IndependentWorker
from work.models.work_co import WorkCo
from work.models.work_co_worker import WorkCoWorker
from work.models.work_line_item import WorkLineItem, get_work_line_item_lookup
from rentals.models import Building
from typeform.models import Response as TypeformResponse
from util.fields import OneToOneOrNoneField
from util.templatetags.util_extras import currency
from util.timezone import now, describe_timedelta
from util.urls import keys_url


@receiver(post_save)
def post_save(sender, instance, *args, **kwargs):
  # THIS IS WHERE PAYMENTS GET CREATED!!! LOOK AT ME!!!
  if issubclass(sender, Work):
    payment = WorkPayment.objects.get_or_create_payment(instance)
    if payment:
      payment.update_sales_tax()
  # THESE ARE WHERE SALES TAX GETS UPDATED!!!
  elif issubclass(sender, Payment):
    # Danger of an infinite loop if this itself causes a save on a payment.
    instance.update_sales_tax()
  elif issubclass(sender, WorkLineItem):
    work = instance.work
    if work.workpayment_or_none:
      work.workpayment.update_sales_tax()


UNSENT = 'UNSENT'
SUCCESS = 'SUCCESS'
PENDING = 'PENDING'
NOT_REQUIRED = 'NOT REQUIRED'
STATUSES = [
    SUCCESS, UNSENT, PENDING, INSUFFICIENT_FUNDS, RECEIVER_UNREGISTERED,
    NOT_REQUIRED, RISK_DECLINE]


class Payment(models.Model):
  """ These get created when work gets completed in the case of WorkPayments,
  or manually on the website in the case of ManualPayments. """
  created_at = models.DateTimeField(auto_now_add=True, db_index=True)

  # Yeah, this isn't ideal having work know about paypal, but I feel like the
  # additional layer of abstraction it would take to remove that dependency is
  # probably more work than it's worth. Let's keep paypal limited to payment.py
  # and test_payment.py at least.
  paypal_payout = OneToOneOrNoneField(
      Payout, on_delete=models.CASCADE, blank=True, null=True, help_text=(
          'Create a payout at the moment of payment.'))

  # Turns out it takes 3 to 5 (or more!) business days to transfer money into
  # the Paypal account for it to be ready for the payouts API. So when that
  # breaks down, like, all the time, allow Tom to just use the Paypal user
  # interface to send money directly from our bank account and log that info
  # here.
  manual_paypal_transaction_id = models.CharField(
      max_length=200, default='', blank=True, help_text=(
          'If you paid this out manually on Paypal\'s website, find the '
          'transaction ID and save it here. Then keys will consider this '
          'payment a SUCCESS. PLEASE make sure the transaction amount is '
          'precisely the same as this payout.'))
  manual_paypal_transaction_when = models.DateTimeField(
      blank=True, null=True, help_text=(
          'When did you pay this out manually on Paypal\'s website?'))

  on_hold_reason = models.TextField(default='', blank=True, help_text=(
      'Why should we not send out this payment just yet?'))
  notes = models.TextField(default='', blank=True, help_text=(
      'This simply shows up in lists.'))
  # Old payments didn't have this concept of sales tax.
  sales_tax = MoneyField(
      max_digits=10, decimal_places=2, default_currency='USD',
      default=Money('0', 'USD'))
  # Did we just now tell a background thread to send this payment?
  sending = False

  def clean(self):
    super().clean()
    if int(bool(self.manual_paypal_transaction_id)) + int(
        bool(self.manual_paypal_transaction_when)) == 1:
      raise ValidationError(
          'If you paid this out manually, you have to fill in both '
          '"Manual paypal transaction id" and '
          '"Manual paypal transaction when"')

  def get_work_started(self):
    raise NotImplementedError('get_work_started')

  def get_work_completed(self):
    raise NotImplementedError('get_work_completed')

  def invoice_number(self):
    return '{}{}'.format(self.invoice_prefix(), self.pk)

  def invoice_prefix(self):
    raise NotImplementedError('invoice_prefix')

  def remitance_number(self):
    """ I'm just writing this down so I remember what it's supposed to be
    called. But when we batch up payments into a single payout, that payout
    will have a Remitance# """
    raise NotImplementedError('remitance_number')

  def get_child_class_instance(self):
    if self.__class__ != Payment:
      # If you do select_related('payment__workpayment'), then
      # .payment.workpayment won't require an additional sql query. So far so
      # good. But if you do .payment.workpayment.workpayment, it WILL require
      # an additional SQL query.
      return self
    try:
      return self.workpayment
    except Payment.workpayment.RelatedObjectDoesNotExist:
      pass
    try:
      return self.manualpayment
    except Payment.manualpayment.RelatedObjectDoesNotExist:
      pass
    raise Exception('I cant figure out what type of Payment this is')

  def success(self):
    return self.manual_paypal_transaction_id or (
        self.paypal_payout and self.paypal_payout.success())

  def paid_at(self):
    if self.success():
      if self.manual_paypal_transaction_id:
        return self.manual_paypal_transaction_when
      return self.paypal_payout.when_did
    return ''

  def pending(self):
    return self.sending or (
        self.paypal_payout and self.paypal_payout.pending())

  def status(self):
    if self.full_time_employee():
      return NOT_REQUIRED
    if self.success():
      return SUCCESS
    if self.paypal_payout:
      return self.paypal_payout.status()
    return UNSENT

  def tried_to_send(self):
    return self.paypal_payout and self.paypal_payout.batch_status

  def require_payment(self):
    if self.on_hold_reason or self.success() or self.pending() or (
        self.full_time_employee() or self.manual_paypal_transaction_id):
      return False
    return True

  def full_time_employee(self):
    worker = self.get_worker()
    if not worker:
      return False
    if worker.__class__ == Worker:
      worker = worker.get_child_class_instance()
    return isinstance(worker, IndependentWorker) and worker.full_time_employee

  def retry_pay(self, paypal_api=None):
    if self.success():
      raise Exception('Why are you retrying a successful payment?')
    if self.paypal_payout:
      if self.paypal_payout.success():
        raise Exception('Why are you retrying a successful payment?')
      if not self.paypal_payout.is_sent():
        raise Exception((
            'payment {} was never sent in the first place so its weird that '
            'youre asking me to retry.').format(self.pk))
    self._init_new_payout()
    self.paypal_payout.send(api=paypal_api)

  def pay(self, paypal_api=None):
    if self.on_hold_reason:
      raise Exception('You cant make a payment thats on hold.', self.pk)
    if self.success():
      raise Exception('Why are you trying to pay a SUCCESS payment?')
    if self.paypal_payout:
      if self.paypal_payout.is_sent():
        raise Exception('This payment was already paid.', self.pk)
    else:
      self._init_new_payout()
    self.paypal_payout.send(api=paypal_api)

  def _init_new_payout(self):
    if self.manual_paypal_transaction_id:
      raise Exception(
          'This was paid out manually. Dont init a new payout for it.')
    # Paypal throws an error if you try to give it an email_subject with gt 255
    # chars.
    self.paypal_payout = Payout.objects.init_new_payout(
        pay_email=self.get_payment_email(), amount=self.get_total_amount(),
        email_subject=self.get_subject()[:255], note=self.get_message(),
        when_should=now())
    self.save()

  def worker_work_co(self):
    worker = self.get_worker()
    if worker:
      worker = worker.get_child_class_instance()
      if isinstance(worker, WorkCoWorker):
        return worker.work_co

  def get_worker(self):
    raise NotImplementedError('get_worker')

  def is_work_co(self):
    raise NotImplementedError('is_work_co')

  def get_work_co(self):
    return self.is_work_co()

  def vendor_name(self):
    if self.is_work_co():
      work_co = self.get_work_co()
      if work_co:
        return work_co.name
    else:
      worker = self.get_worker()
      if worker:
        return worker.name

  def can_calculate_duration(self):
    raise NotImplementedError('can_calculate_duration')

  def can_calculate_amount(self):
    raise NotImplementedError('can_calculate_amount')

  def get_paid_out_amount(self):
    if self.paypal_payout:
      return self.paypal_payout.amount
    if self.manual_paypal_transaction_id:
      return self.get_total_amount()

  def get_total_amount(self, work_line_item_lookup=None):
    if self.paypal_payout:
      return self.paypal_payout.amount
    return sum([
        self.get_main_amount(), self.get_line_item_amount(
            work_line_item_lookup=work_line_item_lookup), self.sales_tax])

  def get_main_amount(self):
    raise NotImplementedError('get_main_amount')

  def get_line_items(self, work_line_item_lookup=None):
    return []

  def get_line_item_amount(self, work_line_item_lookup=None):
    line_items = self.get_line_items(
        work_line_item_lookup=work_line_item_lookup)
    if line_items:
      return sum([li.amount for li in line_items])
    return Money('0', 'USD')

  def update_sales_tax(self):
    # This gets updated on a post_save signal for payments. But also this might
    # save a payment. So only call save if it actually changes to avoid an
    # infinite loop.
    if not self.success() and self.can_calculate_amount():
      new_sales_tax = self.calc_sales_tax()
      if self.sales_tax != new_sales_tax:
        self.sales_tax = new_sales_tax
        self.save()

  def calc_sales_tax(self):
    raise NotImplementedError('calc_sales_tax')

  def get_payment_email(self):
    raise NotImplementedError('get_payment_email')

  def get_subject(self):
    raise NotImplementedError('get_subject')

  def get_message(self):
    raise NotImplementedError('get_message')

  def get_description(self):
    raise NotImplementedError('get_description')

  def get_invoice_description(self):
    raise NotImplementedError('get_invoice_description')

  def get_rental(self):
    raise NotImplementedError('get_rental')

  def get_work_url(self):
    raise NotImplementedError('get_work_url')

  def get_bill_to_building(self):
    raise NotImplementedError('get_bill_to_building')

  def admin_url(self):
    raise NotImplementedError('admin_url')

  def keys_url(self):
    return keys_url(self.admin_url())

  class Meta:
    ordering = ('-created_at',)


class WorkPaymentManager(models.Manager):
  def get_or_create_payment(self, work):
    existing = self.filter(work=work).first()
    if existing:
      return existing
    if work.completed_at:
      return self.create(work=work)


class WorkPayment(Payment):
  work = OneToOneOrNoneField(Work, on_delete=models.CASCADE)
  hours_override = models.DecimalField(
      decimal_places=2, max_digits=5, null=True, blank=True, help_text=(
          'Sometimes mistakes get made tracking time.'))

  objects = WorkPaymentManager()

  def invoice_prefix(self):
    return self.work.get_child_class_instance().invoice_prefix()

  def get_work_started(self):
    return self.work.started_at

  def get_work_completed(self):
    return self.work.completed_at

  def describe_amount(self, work_line_item_lookup=None):
    to_return = []
    if self.is_work_co():
      to_return.extend([currency(self.get_main_amount()), ' flat rate'])
    else:
      to_return.extend([currency(self.get_worker().hour_rate), ' * '])
      if self.hours_override:
        # unsupported type for timedelta hours component: decimal.Decimal
        to_return.extend([
            describe_timedelta(timedelta(hours=float(self.hours_override))),
            ' (hours override)'])
      else:
        duration = self.work.get_actual_duration()
        min_duration = timedelta(hours=self.get_worker().hour_min)
        if duration >= min_duration:
          to_return.append(describe_timedelta(duration))
        else:
          to_return.extend([
              describe_timedelta(min_duration), ' (hour minimum)'])
    line_item_amount = self.get_line_item_amount(
        work_line_item_lookup=work_line_item_lookup)
    if line_item_amount:
      to_return.extend([' + ', currency(line_item_amount), ' line items'])
    if self.sales_tax:
      to_return.extend([' + ', currency(self.sales_tax), ' tax'])
    return ''.join(to_return)

  def get_readable_type(self):
    return 'WorkPayment'

  def get_reported_hours(self):
    return self.work.get_actual_duration().seconds / 3600

  def get_billable_hours(self):
    if self.hours_override:
      return self.hours_override
    return max(
        self.get_reported_hours(),
        self.get_worker().get_child_class_instance().get_hour_min())

  def explain_why_cant_calculate_amount(self):
    if self.hours_override:
      return
    if self.is_work_co():
      rental = self.work.get_child_class_instance().get_rental()
      if not rental.properlyrental:
        return 'There\'s no properly rental for this rental'
      if not rental.properlyrental.cleaning_flat_rate:
        return (
            'This is a cleaning work_co job, but the cleaning_flat_rate '
            'isn\'t set.')
    else:
      if not self.get_worker():
        return (
            'This job doesn\'t say who accepted it so I don\'t know the '
            'minimum billable hours.')
      return self.work.explain_why_cant_calculate_duration()

  def can_calculate_duration(self):
    return not self.work.explain_why_cant_calculate_duration()

  def can_calculate_amount(self):
    return not bool(self.explain_why_cant_calculate_amount())

  def _get_work_co_amount(self):
    rental = self.work.get_child_class_instance().get_rental()
    return rental.properlyrental.cleaning_flat_rate

  def get_main_amount(self):
    if self.is_work_co():
      return self._get_work_co_amount()
    return round(
        Decimal(self.get_billable_hours()) * self.get_worker().hour_rate, 2)

  def get_line_items(self, work_line_item_lookup=None):
    if self.work:
      if not work_line_item_lookup:
        work_line_item_lookup = get_work_line_item_lookup([self.work])
      return work_line_item_lookup.get(self.work_id, [])
    return []

  def calc_sales_tax(self):
    return (self._tax_rate() / 100) * self._taxable_amount()

  def _tax_rate(self):
    work = self.work.get_child_class_instance()
    return work.tax_rate()

  def _taxable_amount(self):
    taxable = self.get_main_amount()
    if taxable is None:
      # This is probably a configuration issue.
      return Money(0, 'USD')
    for line_item in self.work.worklineitem_set.filter(charge_sales_tax=True):
      taxable += line_item.amount
    return taxable

  def get_worker(self):
    return self.work.accepted_by and (
        self.work.accepted_by.get_child_class_instance())

  def is_work_co(self):
    # If there's a worker associated with this payment, easy. We can just check
    # if they're independent. But if we don't know the worker due to some bug,
    # we do the next best thing and ask the job itself if it's supposed to be
    # done by a work co.
    if self.get_worker():
      return self.worker_work_co()
    return self.work and self.work.uses_work_co() and self.work.get_work_co()

  def get_payment_email(self):
    return self.get_worker().get_payment_email()

  def get_subject(self):
    return self.get_message()

  def get_message(self):
    work = self.work.get_child_class_instance()
    at = ''
    if work.get_rental():
      at = work.get_rental().nickname
    elif work.get_building():
      at = work.get_building().nickname
    return '{} at {} on {}'.format(
        work.get_readable_work_title(), at,
        work.completed_at.date() if work.completed_at else '???')

  def get_description(self):
    return self.work.get_child_class_instance().get_readable_work_title()

  def get_invoice_description(self):
    return self.get_message()

  def get_rental(self):
    return self.work.get_child_class_instance().get_rental()

  def get_work_url(self):
    return self.work and self.work.get_child_class_instance().url()

  def get_bill_to_building(self):
    return self.work.get_child_class_instance().get_bill_to_building()

  def admin_url(self):
    return '/admin/work/workpayment/{}/change/'.format(self.pk)


class ManualPayment(Payment):
  subject = models.CharField(max_length=200)
  message = models.TextField()

  # This would ideally be IndependentWorker now, but let's tackle that later.
  # In the meantime, the ManualPaymentForm only lets in IndependentWorkers.
  worker = models.ForeignKey(
      Worker, on_delete=models.PROTECT, null=True, blank=True, help_text=(
          'Who gets paid? Specify either a worker or a work_co.'))
  work_co = models.ForeignKey(
      WorkCo, on_delete=models.PROTECT, null=True, blank=True, help_text=(
          'Who gets paid? Specify either a worker or a work_co.'))
  # For instance,
  # https://keys.hihoward.com/admin/work/manualpayment/297/change/ is
  # a bonus which doesn't really apply to a building.
  building = models.ForeignKey(
      Building, on_delete=models.PROTECT, null=True, blank=True, help_text=(
          'What building does this payment link back to, if any?'))
  receipt_photo_url = models.CharField(max_length=400, blank=True, default='')
  amount = MoneyField(max_digits=10, decimal_places=2, default_currency='USD')
  typeform_response = OneToOneOrNoneField(
      TypeformResponse, on_delete=models.PROTECT, null=True, blank=True,
      help_text=(
          'Keep track so we dont get duplicate manual payments for the same '
          'response.'))
  work_completed = models.DateTimeField(help_text=(
      'When did this actually happen?'))

  def invoice_prefix(self):
    return 'mp'

  def get_work_started(self):
    return None

  def get_work_completed(self):
    return self.work_completed

  def clean(self):
    super().clean()
    if int(bool(self.worker)) + int(bool(self.work_co)) != 1:
      raise ValidationError(
          'Specify precisely one of either worker or work_co.')

  def save(self, *args, **kwargs):
    super().save(*args, **kwargs)
    if self.worker:
      try:
        self.worker.workcoworker
        log_error(
            'Somebody created a manual payment to a WorkCoWorker',
            'Figure out what to do about that. {}'.format(self.pk))
      except Worker.workcoworker.RelatedObjectDoesNotExist:
        pass

  def get_readable_type(self):
    return 'ManualPayment'

  def can_calculate_duration(self):
    return False

  def can_calculate_amount(self):
    return True

  def get_main_amount(self):
    return self.amount

  def calc_sales_tax(self):
    return Money('0', 'USD')

  def get_payment_email(self):
    if self.work_co:
      email = self.work_co.owner.email
      if not email:
        subject = ((
            'User {} needs an email address in order for {} to get '
            'paid').format(self.work_co.owner.username, self.work_co.name))
        notify(settings.ALERT_SERVICE_PROVIDER_NEEDS_PAYPAL, subject)
      return email
    return self.worker.get_child_class_instance().get_payment_email()

  def get_worker(self):
    return self.worker

  def is_work_co(self):
    return self.work_co or self.worker_work_co()

  def get_subject(self):
    return self.subject

  def get_message(self):
    return self.message

  def get_description(self):
    if self.get_subject() == self.get_message():
      return self.get_subject()
    return '{} {}'.format(self.get_subject(), self.get_message())

  def get_invoice_description(self):
    return self.get_description()

  def get_rental(self):
    return None

  def get_work_url(self):
    return None

  def get_bill_to_building(self):
    return self.building

  def admin_url(self):
    return '/admin/work/manualpayment/{}/change/'.format(self.pk)
