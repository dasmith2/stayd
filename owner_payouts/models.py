from abc import abstractmethod
from datetime import timedelta, date

from django.db import models
from django.utils import timezone
from djmoney.money import Money
from pays.models import PaypalPayout
from rentals.models import Owner
from reservations.models import Reservation, ReservationAdjustment


class OwnerPayout(PaypalPayout):
  """ At this point, you could definitely get away with just calling the
  PaypalPayout table the Owner Payout table in the Meta class because that's
  all we use it for. But this is nice and clear. Now we have an OwnerPayout
  table to point the admin at and we leave the door open for using the
  PaypalPayout to pay other people for other things. """

  def calculate_amount_and_save(self):
    if self.paid_out_already():
      raise Exception(
          'You can\'t update the amount on a payout that already happened.')
    res_pays = ReservationToPayout.objects.filter(payout=self)
    res_adjusts = ReservationAdjustmentToPayout.objects.filter(payout=self)
    amount = Money(0, 'USD')
    owner = None
    payout_rule = None
    for res in res_pays:
      reservation_owner = res.get_listing().rental.owner
      if not owner:
        owner = reservation_owner
        payout_rule = res.get_applicable_payout_rule()
      elif reservation_owner.id != owner.id:
        raise Exception(
            'You can\'t have more than one owner in a payout. {} vs {}'.format(
                reservation_owner.id, owner.id))
      amount += payout_rule.percent * res.reservation.total_payin
    for adjust in res_adjusts:
      amount += payout_rule.percent * adjust.adjustment.amount
    self.amount = amount
    self.save()


class PayoutRule(models.Model):
  percent = models.DecimalField(decimal_places=4, max_digits=5, help_text=(
      'What percent of the rental income does the owner receive? Between '
      '0.0 and 1.0'))
  days_after_payment = models.PositiveIntegerField(help_text=(
      'How many days after we got paid do they get paid?'))
  goes_into_effect = models.DateTimeField()
  owner = models.ForeignKey(Owner, on_delete=models.CASCADE)

  def __str__(self):
    return 'Pay {} {}% {} days after we get paid starting {}'.format(
        self.owner, int(self.percent * 100), self.days_after_payment,
        self.goes_into_effect)


class Payoutable(models.Model):
  payout = models.ForeignKey(
      OwnerPayout, on_delete=models.CASCADE, null=True, help_text=(
          'The payout that this is reflected on.'))

  @abstractmethod
  def get_listing(self):
    raise NotImplementedError('get_listing')

  @abstractmethod
  def transaction_on(self):
    raise NotImplementedError('transaction_on')

  def get_applicable_payout_rule(self):
    owner = self.get_listing().rental.owner
    if not owner:
      return
    payout_rules = PayoutRule.objects.filter(owner=owner)
    if not payout_rules:
      return
    if len(payout_rules) > 1:
      raise Exception("Not sure how to handle more than one payout rule yet.")
    payout_rule = payout_rules[0]
    if payout_rule.goes_into_effect > self.transaction_on():
      return
    return payout_rule

  def explain_why_no_payout(self):
    if self.payout:
      return
    owner = self.get_listing().rental.owner
    if not owner:
      return 'Nobody owns {}'.format(
          self.listing.rental.airbnb_address_scrape)
    payout_rules = PayoutRule.objects.filter(owner=owner)
    if not payout_rules:
      return '{} doesn\'t have any payout rules.'.format(owner.name)
    payout_rule = payout_rules[0]
    if payout_rule.goes_into_effect > self.transaction_on():
      return (
          'The payout rule go into effect on {} '
          'and we saw this transaction on {}.').format(
          payout_rule.goes_into_effect, self.transaction_on())

  class Meta:
    abstract = True


class ReservationToPayoutManager(models.Manager):
  def get_for_reservation(self, reservation):
    return self.get_or_create(reservation=reservation)[0]


class ReservationToPayout(Payoutable):
  reservation = models.OneToOneField(Reservation, on_delete=models.CASCADE)

  objects = ReservationToPayoutManager()

  def transaction_on(self):
    return self.reservation.when_did_we_get_paid()

  def get_listing(self):
    return self.reservation.listing

  def update_payout(self):
    """ This creates payouts as necessary. If the payout is already paid,
    don't update anything without understanding why you'd update it. For
    instance, the amount could change if the percentage paid out changed,
    but if we've already paid this one out, you wouldn't want to automatically
    create an adjustment or anything. """
    payout = self._get_payout()
    if not payout:
      return
    if payout.paid_out_already():
      return
    payout.calculate_amount_and_save()

  def explain_why_no_payout(self):
    if self.payout:
      return
    if not self.reservation.when_did_we_get_paid():
      return 'We didn\'t get paid yet.'
    return super(ReservationToPayout, self).explain_why_no_payout()

  def _get_payout(self):
    if self.payout:
      return self.payout
    if not self.reservation.when_did_we_get_paid():
      return
    payout_rule = self.get_applicable_payout_rule()
    if not payout_rule:
      return
    pay_after_days = timedelta(payout_rule.days_after_payment)
    ideally_payout_on = (
        self.reservation.when_did_we_get_paid() + pay_after_days).date()
    payout_on = max(ideally_payout_on, date.today())
    payouts = OwnerPayout.objects.filter(
        who_to_pay=self.get_listing().rental.owner, when_should=payout_on,
        when_did=None)
    if payouts:
      payout = payouts[0]
    else:
      payout = OwnerPayout.objects.create(
          who_to_pay=self.get_listing().rental.owner, amount=Money(0, 'USD'),
          when_should=payout_on,
          when_did=None)
    self.payout = payout
    self.save()
    return payout


class ReservationAdjustmentToPayoutManager(models.Manager):
  def assign_adjustments(self):
    # Assign the biggest (a.k.a. most negative) adjustments first because
    # they're the hardest to find a home for. I can see this being a
    # performance issue if we get a ton of these and we're digging through
    # this big table with big joins and an ever increasing backlog of useless
    # adjustments that will never find a home. But I won't prematurely
    # optimize.
    adjustments = ReservationAdjustment.objects.filter(
        reservationadjustmenttopayout__payout=None,
        listing__rental__owner__isnull=False).order_by('amount')
    for adjustment in adjustments:
      adjust_to_payout = self.get_or_create(
          reservation_adjustment=adjustment)[0]
      owner = adjust_to_payout.get_listing().rental.owner
      payout_rule = adjust_to_payout.get_applicable_payout_rule()
      if payout_rule:
        adjust_amount = payout_rule.percent * adjustment.amount
        # At first we're just going to let these payouts sit around on
        # hold, so we'll have some old unsent payouts sitting around
        # probably forever.
        possible_payouts = OwnerPayout.objects.filter(
            who_to_pay=owner, when_did=None, when_should__gt=timezone.now())
        for payout in possible_payouts:
          breathing_room = payout.amount + adjust_amount
          if breathing_room >= Money(0, 'USD'):
            adjustment.payout = payout
            adjustment.save()
            payout.amount += adjust_amount
            payout.save()


class ReservationAdjustmentToPayout(Payoutable):
  reservation_adjustment = models.OneToOneField(
      ReservationAdjustment, on_delete=models.CASCADE)

  objects = ReservationAdjustmentToPayoutManager()

  def transaction_on(self):
    return self.reservation_adjustment.when

  def get_listing(self):
    return self.reservation_adjustment.listing
