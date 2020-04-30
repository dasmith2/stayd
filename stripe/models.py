"""
Payouts have a list of BalanceTransactions. Charges have a BalanceTransaction.
So we have to sync Payouts separate from Charges and then link up the
BalanceTransactions. This explains why Stripe doesn't show the Payout for a
Charge!

Matching Charges to Payments became a whole thing. That could stand to be split
into a separate file.
"""
from datetime import timedelta
import json

from django import forms
from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.shortcuts import reverse
from util.timezone import now
from djmoney.models.fields import MoneyField
from djmoney.money import Money

from errors.models import log_error, Notifier
from reservations.models import (
    Payment, CreditCardFee, Reservation, Refund as ReservationRefund,
    ResolutionCategory)
from reservations.syncer import ReservationManagerIsDown
from stripe.api import API
from util.background import background
from util.fields import OneToOneOrNoneField
from util.signals import post_sync
from util.table import Table, Cell
from util.timezone import ts_to_utc_dt, str_to_tz_dt
from util.urls import keys_reverse


@background
def sync_stripe_background():
  # Maybe charges were refunded or something in the last few weeks, I don't
  # know.
  sync_all(since=now() - timedelta(days=60))


@background
def alert_unlinked_charges_background(notifier=None, nnow=None):
  notifier = notifier or Notifier()
  nnow = nnow or now()
  if not len(list(unlinked_charges(nnow=nnow))):
    return
  # Somebody takes a payment for a booking.com reservation directly on Stripe
  # (which they aren't supposed to do, but it happens), so Guesty never hears
  # about it. So that reservation shows up in the ideal payin != likely payin
  # list, which tends to go unchecked for months. Finally somebody checks the
  # payin problem list and they realize somebody did take payment so they enter
  # a manual charge without credit card info just so Guesty has that record and
  # the reservation leaves the payment problem list. Now keys has a "new"
  # months old payment. So take a stab at resolving this here situation by just
  # looking back in time a little further.
  Charge.objects.match_charges_to_payments(nnow - timedelta(days=365))
  problem_count = len(list(unlinked_charges()))

  if problem_count:
    message = (
        'There are {} erroneous Stripe charges. The last time this happened '
        'it was because Guesty double charged our guests. '
        'See {} for details.'.format(
            problem_count, keys_reverse('over_charges')))
    notifier.notify(
        settings.ALERT_LIKELY_PAYIN_NOT_IDEAL,
        'Guests over-charged in Stripe', message)


def unlinked_charges_table(nnow=None):
  table = Table([
      'Resolve me', 'Amount', 'When', 'Stripe Charge ID', 'Last 4', 'CC brand',
      'Identical payment found in reservation'])
  for charge in unlinked_charges(nnow=nnow):
    suspected_reservation_cell = Cell()
    matches_payment = suspected_matched_payment(charge)
    if matches_payment:
      res = matches_payment.reservation
      suspected_reservation_cell = Cell(
          res.guest.get_name(), url=res.admin_url())
    resolve_url = reverse(
        'resolve_unlinked_charge', kwargs={'charge_id': charge.pk})
    table.create_row([
        Cell('Resolve me', url=resolve_url),
        charge.amount, charge.created, charge.charge_id, charge.cc_last_4,
        charge.cc_brand, suspected_reservation_cell])
  return table


def suspected_matched_payment(charge):
  return Payment.objects.filter(
      amount=charge.amount, paid_at__date=charge.created.date(),
      cc_last_4=charge.cc_last_4, cc_brand=charge.cc_brand).first()


def unlinked_charges(nnow=None):
  """ Every stripe charge should have a corresponding Payment, meaning, every
  stripe charge should be for an actual bill. This isn't always the case when
  mistakes get made. Guesty has been known to double charge. """
  nnow = nnow or now()
  for charge in Charge.objects.filter(
      payment__isnull=True, unlinkedchargeresolution__isnull=True,
      created__lt=nnow - timedelta(days=3),
      created__gte=str_to_tz_dt('2018-12-01')):
    if charge.amount_minus_refunds():
      yield charge


def sync_all(since=None, api=API()):
  for payout in Payout.objects.sync(since, api):
    payout.sync_balance_transactions(api)
  Charge.objects.sync(since, api)
  Charge.objects.sync_refunds(api)

  Charge.objects.unlink_siblings_of_unmatched()
  Charge.objects.match_charges_to_payments(since)
  try:
    Charge.objects.sync_almost_matched_reservations()
  except ReservationManagerIsDown:
    pass  # This step is kind of a stab in the dark anyway.
  Charge.objects.match_charges_to_payments(since)


def _get_since(since):
  return since or str_to_tz_dt('2000-01-01 00:00')


class PayoutManager(models.Manager):
  def sync(self, since, api):
    to_return = []
    since = _get_since(since)
    for payout_data in api.get_payouts():
      status = payout_data['status']
      if status == 'paid':
        payout = self._from_data(payout_data)
        if payout.arrival_date < since:
          break
        existing = self.filter(payout_id=payout.payout_id).first()
        if existing:
          payout.pk = existing.pk
        payout.save()
        to_return.append(payout)
      elif status not in ['in_transit']:
        log_error(
            'Unexpected payout status', '{}\n{}'.format(status, payout_data))
    return to_return

  def sync_balance_transactions(self, api):
    to_return = []
    for payout in self.filter(balance_transactions_synced_at__isnull=True):
      to_return.extend(payout.sync_balance_transactions(api))
    return to_return

  def _from_data(self, data):
    for field in ['failure_balance_transaction', 'failure_code']:
      if data[field]:
        log_error(
            'Unexpected payout {}'.format(field),
            '{}'.format(data))
    return Payout(
        payout_id=data['id'],
        amount=Money(data['amount'] / 100, data['currency'].upper()),
        arrival_date=ts_to_utc_dt(data['arrival_date']))


class Payout(models.Model):
  payout_id = models.CharField(max_length=200, db_index=True, unique=True)
  amount = MoneyField(
      max_digits=10, decimal_places=2, default_currency='USD')
  arrival_date = models.DateTimeField()
  balance_transactions_synced_at = models.DateTimeField(
      null=True, blank=True, db_index=True, help_text=(
          'When did we successfully call sync_balance_transactions on this '
          'payout?'))

  objects = PayoutManager()

  def stripe_url(self):
    return 'https://dashboard.stripe.com/payouts/{}'.format(self.payout_id)

  def sync_balance_transactions(self, api):
    to_return = []
    for bt_data in api.get_balance_transactions(self.payout_id):
      balance_transaction = (
          BalanceTransaction.objects.balance_transaction_from_data(bt_data))
      # This balance transaction may have been synced already as part of a
      # charge.
      existings = BalanceTransaction.objects.filter(
          balance_transaction_id=balance_transaction.balance_transaction_id)
      existing = existings.first()
      if existing:
        balance_transaction.pk = existing.pk
      balance_transaction.payout = self
      balance_transaction.save()
      to_return.append(balance_transaction)
      fee_datas = bt_data['fee_details']
      for fee_data in fee_datas:
        Fee.objects.get_or_create(
            balance_transaction=balance_transaction,
            description=fee_data['description'],
            amount=Money(
                fee_data['amount'] / 100, fee_data['currency'].upper()))
      if len(fee_datas) != Fee.objects.filter(
          balance_transaction=balance_transaction).count():
        log_error(
            'The fees changed. We need smarter fee merging.',
            'Payout {}, BalanceTransaction {}'.format(
                self.pk, balance_transaction.pk))
      to_return.append(balance_transaction)
    self.balance_transactions_synced_at = now()
    self.save()
    return to_return

  class Meta:
    ordering = ('-arrival_date',)


CHARGE = 'charge'
PAYOUT = 'payout'
TRANSACTION_TYPE_CHOICES = (
    (CHARGE, CHARGE),
    (PAYOUT, PAYOUT))


class BalanceTransactionManager(models.Manager):
  def balance_transaction_from_data(self, data):
    bt = BalanceTransaction(
        balance_transaction_id=data['id'],
        amount=data['amount'] / 100,
        total_fees=data['fee'] / 100,
        net=data['net'] / 100,
        currency=data['currency'].upper(),
        ttype=data['type'],
        status=data['status'])
    return bt

  def get_balance_transaction(self, balance_transaction_id, api):
    balance_transaction = self.filter(
        balance_transaction_id=balance_transaction_id).first()
    if balance_transaction:
      return balance_transaction
    bt_data = api.get_balance_transaction(balance_transaction_id)
    balance_transaction = self.balance_transaction_from_data(bt_data)
    balance_transaction.save()
    return balance_transaction


AVAILABLE = 'available'
PENDING = 'pending'
BALANCE_TRANSACTION_STATUS_CHOICES = (
    (AVAILABLE, AVAILABLE),
    (PENDING, PENDING))


class BalanceTransaction(models.Model):
  balance_transaction_id = models.CharField(
      max_length=200, db_index=True, unique=True)
  payout = models.ForeignKey(
      Payout, on_delete=models.CASCADE, null=True, blank=True)
  amount = models.DecimalField(max_digits=10, decimal_places=2)
  total_fees = models.DecimalField(max_digits=10, decimal_places=2)
  net = models.DecimalField(max_digits=10, decimal_places=2)
  currency = models.CharField(max_length=3, default='USD')
  ttype = models.CharField(max_length=100, choices=TRANSACTION_TYPE_CHOICES)
  status = models.CharField(
      max_length=50, choices=BALANCE_TRANSACTION_STATUS_CHOICES,
      default=AVAILABLE)

  objects = BalanceTransactionManager()

  class Meta:
    ordering = ('-payout__arrival_date',)


class Fee(models.Model):
  balance_transaction = models.ForeignKey(
      BalanceTransaction, on_delete=models.CASCADE)
  description = models.TextField()
  amount = MoneyField(
      max_digits=10, decimal_places=2, default_currency='USD')

  def ensure_credit_card_fee_exists(self):
    charge = self.balance_transaction.charge_or_none
    if charge:
      payment = charge.payment
      if payment:
        CreditCardFee.objects.get_or_create(
            payment=charge.payment,
            description=self.description,
            amount=self.amount)

  class Meta:
    ordering = ('balance_transaction', 'description',)


@receiver(post_save, sender=Fee)
def fee_post_save(sender, instance, *args, **kwargs):
  instance.ensure_credit_card_fee_exists()


class ChargeManager(models.Manager):
  def sync_almost_matched_reservations(self, sync=None):
    """ Guesty doesn't inform us when refunds or successful payments happen.
    Bane of my life. So go through all unmatched charges, see if there are any
    payments that ALMOST match, sync their reservations, and then try to match
    charges again. Maybe it didn't match because a refund landed in the
    meantime and I see that in Stripe but don't see it in Guesty yet because
    they didn't tell us. """
    charges_missing = Charge.objects.filter(payment__isnull=True)
    missing_amounts = [
        data['amount'] for data in charges_missing.values('amount')]
    matching_missing_payments = Payment.objects.filter(
        charge__isnull=True, amount__in=missing_amounts)
    res_id_datas = matching_missing_payments.values('reservation_id')
    reservation_ids = [data['reservation_id'] for data in res_id_datas]
    for reservation in Reservation.objects.filter(pk__in=reservation_ids):
      reservation.sync(sync)

  def unlink_siblings_of_unmatched(self):
    """ Guesty now includes stripe ids in payment information!

    This all goes back to Guesty not including payment ids with payments.
    See https://app.guesty.com/reservations/5bf40d019ad4d0003851888f/financials
    for an example of a reservation with two identical payments on the same day
    except one of the payments later got a $1 refund. I had to unlink that
    particular payment - charge relationship and then re-match everything and
    THEN they lined up. It's possible this relation existed in the first place
    because match_charges_to_payments will match charges to payments with
    different refund statuses IF that's the only option because maybe Stripe
    didn't know about a manual refund that was entered in Guesty. So I think
    the answer is to find every charge that can't find a match, and unlink any
    siblings it has. """
    for charge in Charge.objects.filter(payment__isnull=True):
      for sibling in Charge.objects.filter(
          amount=charge.amount, payment__isnull=False):
        if abs(charge.created - sibling.created) < timedelta(days=2):
          sibling.payment = None
          sibling.save()

  def match_charges_to_payments(self, since):
    since = _get_since(since)
    # So, at first, everything has to match. cc info, and whether or not
    # refunds exist.
    for orphan in self.filter(payment__isnull=True, created__gte=since):
      orphan.match_to_payment()
    # But sometimes, like for reservation
    # https://app.guesty.com/reservations/5bda64a9ae30780040f27fa8/financials
    # we do manual refunds that Stripe isn't able to link to the original
    # charges, but because it's done in Guesty, Guesty is able to link it to
    # the original charges, so in other words reservations knows about refunds
    # but stripe does not.
    for orphan in self.filter(payment__isnull=True, created__gte=since):
      orphan.match_to_payment(pay_attention_to_refunds=False)

  def sync(self, since, api):
    since = _get_since(since)
    to_return = []
    for charge_data in api.get_charges():
      charge = self._sync_charge_data(charge_data, api)
      # It might not be a captured charge in which case we just ignore it.
      if charge:
        to_return.append(charge)
        if charge.created < since:
          break
    return to_return

  def sync_charge(self, charge_id):
    api = API()
    charge_data = api.get_charge(charge_id)
    return self._sync_charge_data(charge_data, api)

  def _sync_charge_data(self, charge_data, api):
    if charge_data['captured'] and charge_data['status'] != 'failed':
      charge = self._from_data(charge_data, api)
      existing = self.filter(charge_id=charge.charge_id).first()
      if existing:
        charge.pk = existing.pk
      charge.save()
      return charge

  def sync_refunds(self, api):
    to_return = []
    for charge in self.filter(
        amount_refunded__gt=0, refunds_synced_at__isnull=True):
      to_return.extend(charge.sync_refunds(api))
    return to_return

  def _from_data(self, data, api):
    if data['status'] != 'succeeded':
        log_error(
            'Unexpected charge data', 'status is {}.\n{}'.format(
                data['status'], data))
    for field in ['application_fee', 'failure_code', 'fraud_details']:
      if data[field]:
        log_error(
            'Unexpected charge data', '{} is nonzero.\n{}'.format(field, data))
    balance_transaction = BalanceTransaction.objects.get_balance_transaction(
        data['balance_transaction'], api)
    currency = data['currency'].upper()
    payment = Payment.objects.filter(payment_provider_id=data['id']).first()
    last4 = None
    brand = None
    if 'last4' in data['source']:
      last4 = data['source']['last4']
      brand = data['source']['brand']
    else:
      last4 = data['source']['card']['last4']
      brand = data['source']['card']['brand']

    if not last4:
      log_error('Stripe data missing last4', json.dumps(data, indent=2))
    return Charge(
        charge_id=data['id'],
        balance_transaction=balance_transaction,
        amount=Money(data['amount'] / 100, currency),
        amount_refunded=Money(data['amount_refunded'] / 100, currency),
        created=ts_to_utc_dt(data['created']),
        cc_last_4=last4,
        cc_brand=brand,
        dispute_id=data['dispute'],
        description=data['description'],
        payment=payment)


class Charge(models.Model):
  charge_id = models.CharField(max_length=200, db_index=True, unique=True)
  balance_transaction = OneToOneOrNoneField(
      BalanceTransaction, on_delete=models.CASCADE)
  amount = MoneyField(
      max_digits=10, decimal_places=2, default_currency='USD')
  refunds_synced_at = models.DateTimeField(
      null=True, blank=True, db_index=True, help_text=(
          'When did we successfully call sync_refunds on this charge?'))
  amount_refunded = MoneyField(
      max_digits=10, decimal_places=2, default_currency='USD', db_index=True)
  created = models.DateTimeField(db_index=True, help_text=(
      'Created on Stripe, not created in this database'))
  description = models.TextField(null=True, blank=True, help_text=(
      'Ive only seen this set on authorization holds we cashed in'))
  # cc_last_4 and cc_brand are how we match Charges to Reservations.
  cc_last_4 = models.CharField(max_length=4, db_index=True)
  cc_brand = models.CharField(max_length=20, db_index=True)
  # The point of hooking up to Stripe is mainly to get credit card fees per
  # reservation. Down the road, I can imagine doing clever things with
  # knowledge of disputes. Withholding owner funds until disputes are resolved,
  # that kind of thing. But disputes are rare and we're not totally sure what
  # to do with them at this point. So for now just leave a little note when we
  # notice one, but don't do anything with it.
  dispute_id = models.CharField(
      max_length=200, null=True, blank=True, help_text=(
          'We just write this down for now. Dispute management is, like, v5.'))
  payment = OneToOneOrNoneField(
      Payment, on_delete=models.PROTECT, null=True, blank=True,
      help_text=(
          'The reservation payment we were able to trace this charge back to'))

  objects = ChargeManager()

  def __repr__(self):
    return '<Charge {}: {} {}>'.format(
        self.pk, self.created.date(), self.amount_minus_refunds())

  def __str__(self):
    return self.__repr__()

  def stripe_url(self):
    return 'https://dashboard.stripe.com/payments/{}'.format(self.charge_id)

  def amount_minus_refunds(self):
    return self.amount - self.amount_refunded

  def sync_refunds(self, api):
    to_return = []
    for data in api.get_refunds(self.charge_id):
      balance_transaction = BalanceTransaction.objects.get_balance_transaction(
          data['balance_transaction'], api)
      if data['status'] != 'succeeded':
        log_error(
            'Unexpected refund status', '{}\n{}'.format(data['status'], data))
      refund_id = data['id']
      refund = Refund(
          refund_id=refund_id,
          charge=self,
          balance_transaction=balance_transaction,
          amount=Money(data['amount'] / 100, data['currency'].upper()))
      existing = Refund.objects.filter(refund_id=refund.refund_id).first()
      if existing:
        refund.pk = existing.pk
      reservation_refund = ReservationRefund.objects.filter(
          payment_provider_id=refund_id).first()
      if reservation_refund:
        refund.reservation_refund = reservation_refund
      refund.save()
      to_return.append(refund)
    self.refunds_synced_at = now()
    self.save()
    return to_return

  def has_refunds(self):
    return self.refund_set.exists()

  def match_to_payment(self, pay_attention_to_refunds=True):
    """ Matching charges to payments got way easier once Guesty started
    including the stripe ID in its payments. This function tries to match
    charges to payments without that ID, and it used to do all the matches!
    Now, it rarely comes into play. I keep it around because it's still handy
    in corner cases I guess, like if somebody were to manually take a payment
    on Stripe and then manually enter the amount on Guesty, or something, this
    function would pick up on that.

    See the comments on match_charges_to_payments for a detailed
    explanation of why there are settings for how little detail is required to
    make a match. """
    exact_matches = Payment.objects.filter(
        amount=self.amount, cc_last_4=self.cc_last_4, cc_brand=self.cc_brand)
    # Sometimes payments are taken manually and guesty is unaware of the cc,
    # but other payments were taken with that credit card.
    # https://app.guesty.com/reservations/5b6f0b98009a5d003db1402b/financials
    sibling_payments = Payment.objects.filter(
        cc_last_4=self.cc_last_4, cc_brand=self.cc_brand)
    reservations = set([pay.reservation for pay in sibling_payments])
    sibling_matches = Payment.objects.filter(
        amount=self.amount, cc_last_4__isnull=True, cc_brand__isnull=True,
        reservation__in=reservations)
    # For example this reservation had a manual payment entered on the same day
    # and same amount as a charge that had no other match.
    # https://app.guesty.com/reservations/5c51b3350bb9da001ff32f82/financials
    manual_payment_matches = Payment.objects.filter(
        amount=self.amount, cc_last_4__isnull=True, cc_brand__isnull=True,
        charge__isnull=True, paid_at__date=self.created.date())
    for potential in list(exact_matches) + list(sibling_matches) + (
        list(manual_payment_matches)):
      # At this point, only consider payments with no stripe id attached to
      # them, because those should obviously only be matched purely by unique
      # identifier, not all this clever nonsense.
      if potential.payment_provider_id and self.charge_id and (
          potential.payment_provider_id != self.charge_id):
        continue
      if not pay_attention_to_refunds or (
          self.has_refunds() == potential.has_refunds()):
        if not Charge.objects.filter(payment=potential).exists():
          fees = Fee.objects.filter(
              balance_transaction=self.balance_transaction)
          for fee in fees:
            CreditCardFee.objects.get_or_create(
                payment=potential,
                description=fee.description,
                amount=fee.amount)
          self.payment = potential
          self.save()
          fee_count = fees.count()
          res_fee_count = CreditCardFee.objects.filter(
              payment=potential).count()
          if fee_count != res_fee_count:
            log_error(
                'Wrong CreditCardFee count', (
                    'stripe.Charge {} was matched with reservations.Payment '
                    '{} but there are {} stripe.Fees and {} '
                    'reservation.CreditCardFees').format(
                        self.pk, potential.pk, fee_count, res_fee_count))
          post_sync.send(sender=Reservation, instance=potential.reservation)
          break

  class Meta:
    ordering = ('-created',)


class UnlinkedChargeResolution(models.Model):
  charge = OneToOneOrNoneField(Charge, on_delete=models.CASCADE)
  resolution_category = models.ForeignKey(
      ResolutionCategory, on_delete=models.PROTECT)
  notes = models.TextField(blank=True, null=True)


class UnlinkedChargeResolutionForm(forms.ModelForm):
  class Meta:
    model = UnlinkedChargeResolution
    fields = ['resolution_category', 'notes']


def handle_resolve_unlinked_charge_post(request_post, charge):
  resolution_form = UnlinkedChargeResolutionForm(request_post)
  if resolution_form.is_valid():
    resolution_category = resolution_form.cleaned_data['resolution_category']
    notes = resolution_form.cleaned_data['notes']
    UnlinkedChargeResolution.objects.create(
        charge=charge, resolution_category=resolution_category,
        notes=notes)
    return True


@receiver(post_save, sender=Payment)
def reservation_payment_post_save(sender, instance, *args, **kwargs):
  if instance.payment_provider_id:
    # A payment was saved with a payment_provider_id. Find any existing charge
    # that thought it was for this payment, but turned out not to be due to the
    # payment_provider_id, and dissassociate the charge from the wrong payment.
    # This happens (at the moment) because we didn't used to have ids and there
    # was naturally some confusion when payments with the same amount exist.
    for charge in Charge.objects.filter(
        ~Q(charge_id=F('payment__payment_provider_id')), payment=instance):
      charge.payment = None
      charge.save()
    correct_charge = Charge.objects.filter(
        charge_id=instance.payment_provider_id).first()
    if correct_charge:
      correct_charge.payment = instance
      correct_charge.save()


class Refund(models.Model):
  refund_id = models.CharField(max_length=200, db_index=True, unique=True)
  charge = models.ForeignKey(Charge, on_delete=models.CASCADE)
  balance_transaction = models.ForeignKey(
      BalanceTransaction, on_delete=models.CASCADE)
  amount = MoneyField(
      max_digits=10, decimal_places=2, default_currency='USD')
  reservation_refund = models.ForeignKey(
      ReservationRefund, on_delete=models.PROTECT, null=True, blank=True,
      help_text=(
          'The refund object in the reservations app, if we could find it.'))

  class Meta:
    ordering = ('-charge__created',)

  def __repr__(self):
    return '<Refund {}: {}>'.format(self.pk, self.amount)


@receiver(post_save, sender=ReservationRefund)
def reservation_refund_post_save(sender, instance, *args, **kwargs):
  if instance.payment_provider_id:
    stripe_refund = Refund.objects.filter(
        refund_id=instance.payment_provider_id).first()
    if stripe_refund:
      stripe_refund.reservation_refund = instance
      stripe_refund.save()
