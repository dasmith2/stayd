from abc import abstractmethod
from datetime import timedelta, date

from django.db import models
from django.utils import timezone
from djmoney.models.fields import MoneyField
from djmoney.money import Money
from pays.models import PaypalPayout
from pays.paypal_api import PaypalAPI
from rentals.models import Owner, Rental
from reservations.models import Reservation


class OwnerPayoutManager(models.Manager):
  def send(self, paypal_api=PaypalAPI(), verbose=False):
    for payout in self.filter(
        green_light=True, when_should__lte=date.today(), batch_status=''):
      payout.paypal_api = paypal_api
      if verbose:
        print('Sending payout {} a.k.a. {} in the amount of {} to {}'.format(
            payout.pk, payout.public_id, payout.amount,
            payout.who_to_pay.email))
      payout.send()

  def new_owner_payout(self, owner, when_should):
    payout = self.create(
        who_to_pay=owner, amount=Money(0, 'USD'), when_should=when_should,
        when_did=None)
    payout.compute_public_id()
    return payout


class OwnerPayout(PaypalPayout):
  """ At this point, you could definitely get away with just calling the
  PaypalPayout table the Owner Payout table in the Meta class because that's
  all we use it for. But this is nice and clear. Now we have an OwnerPayout
  table to point the admin at and we leave the door open for using the
  PaypalPayout to pay other people for other things. """

  objects = OwnerPayoutManager()

  def owner(self):
    if self.who_to_pay and self.who_to_pay.pk:
      return Owner.objects.get(pk=self.who_to_pay.pk)

  def adjustments(self):
    return Adjustment.objects.filter(payout=self)

  def reservations_to_payouts(self):
    return ReservationToPayout.objects.filter(payout=self)

  def calculate_amount_and_save(self):
    if self.paid_out_already():
      raise Exception(
          'You can\'t update the amount on a payout that already happened.')
    res_pays = ReservationToPayout.objects.filter(payout=self)
    adjustments = Adjustment.objects.filter(payout=self)
    amount = Money(0, 'USD')
    owner = None
    payout_rule = None
    for res in res_pays:
      reservation_owner = res.get_owner()
      if not owner:
        owner = reservation_owner
        payout_rule = res.get_applicable_payout_rule()
      elif reservation_owner.id != owner.id:
        raise Exception(
            'You can\'t have more than one owner in a payout. {} vs {}'.format(
                reservation_owner.id, owner.id))
      owner_share = payout_rule.percent * res.reservation.total_payin
      res.owner_share = owner_share
      res.our_share = res.reservation.total_payin - owner_share
      res.save()
      amount += owner_share
    for adjustment in adjustments:
      owner_share = payout_rule.percent * adjustment.amount
      adjustment.owner_share = owner_share
      adjustment.our_share = adjustment.amount - owner_share
      amount += owner_share
      adjustment.save()
    self.amount = amount
    self.save()


class PayoutRule(models.Model):
  percent = models.DecimalField(decimal_places=4, max_digits=5, help_text=(
      'What percent of the rental income does the owner receive? Between '
      '0.0 and 1.0'))
  days_after_payment = models.PositiveIntegerField(help_text=(
      'How many days after we got paid do they get paid?'))
  goes_into_effect = models.DateField()
  owner = models.OneToOneField(Owner, on_delete=models.CASCADE)

  def __str__(self):
    return 'Pay {} {}% {} days after we get paid starting {}'.format(
        self.owner, int(self.percent * 100), self.days_after_payment,
        self.goes_into_effect)


class Payoutable(models.Model):
  payout = models.ForeignKey(
      OwnerPayout, on_delete=models.CASCADE, null=True, help_text=(
          'The payout that this is reflected on.'))
  owner_share = MoneyField(
      decimal_places=2, max_digits=10, default_currency='XYZ', help_text=(
          'How much of this does the owner get '
          '(or owe, in the case of debits)'))
  our_share = MoneyField(
      decimal_places=2, max_digits=10, default_currency='XYZ', help_text=(
          'How much of this do we get (or owe, in the case of debits)'))

  @abstractmethod
  def get_owner(self):
    raise NotImplementedError('get_owner')

  @abstractmethod
  def transaction_on(self):
    raise NotImplementedError('transaction_on')

  def get_applicable_payout_rule(self):
    owner = self.get_owner()
    if not owner:
      return
    payout_rules = PayoutRule.objects.filter(owner=owner)
    if not payout_rules:
      return
    if len(payout_rules) > 1:
      raise Exception("Not sure how to handle more than one payout rule yet.")
    payout_rule = payout_rules[0]
    if payout_rule.goes_into_effect > self.transaction_on().date():
      return
    return payout_rule

  def explain_why_no_payout(self):
    if self.payout:
      return
    owner = self.get_owner()
    if not owner:
      return 'Nobody owns {}'.format(
          self.reservation.listing.rental.airbnb_address_scrape)
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
  def update_payout(self, reservation):
    return self.get_for_reservation(reservation).update_payout()

  def get_for_reservation(self, reservation):
    return self.get_or_create(reservation=reservation)[0]


class ReservationToPayout(Payoutable):
  reservation = models.OneToOneField(Reservation, on_delete=models.CASCADE)

  objects = ReservationToPayoutManager()

  def transaction_on(self):
    return self.reservation.when_did_we_get_paid()

  def get_owner(self):
    return self.reservation.listing.rental.owner

  def update_payout(self):
    """ This creates payouts as necessary, adds this reservation to the
    payout, and updates the payout amount. Or, if it was unable to do anything,
    it returns a string explaining why. For instance, if a payout is paid out
    already, obviously you can't update the payout amount. """
    payout = self._get_payout()
    if not payout or payout.paid_out_already():
      return self.explain_why_no_payout()
    payout.calculate_amount_and_save()
    self.refresh_from_db()
    return True

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
        who_to_pay=self.get_owner(), when_should=payout_on,
        when_did=None)
    if payouts:
      payout = payouts[0]
    else:
      payout = OwnerPayout.objects.new_owner_payout(
          self.get_owner(), payout_on)
    self.payout = payout
    self.save()
    return payout


class AdjustmentManager(models.Manager):
  def assign_adjustments(self):
    # Assign the biggest (a.k.a. most negative) adjustments first because
    # they're the hardest to find a home for. I can see this being a
    # performance issue if we get a ton of these and we're digging through
    # this big table with big joins and an ever increasing backlog of useless
    # adjustments that will never find a home. But I won't prematurely
    # optimize.
    adjustments = self.filter(
        payout=None, rental__owner__isnull=False).order_by('amount')
    for adjustment in adjustments:
      owner = adjustment.rental.owner
      payout_rule = adjustment.get_applicable_payout_rule()
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
            payout.calculate_amount_and_save()


class Adjustment(Payoutable):
  """ We pay out Louie on Thursday, but then find out Friday there was an
  issue and Airbnb took a refund back. This is typically due to a
  particular reservation because they're refunding a particular guest, BUT
  Airbnb only tells you the listing for some reason. Since these are, like,
  clawback adjustments, I tack them onto payments whose value is greater
  than the adjustment (well, technically, -1 * the adjustment). """
  amount = MoneyField(
      max_digits=10, decimal_places=2, default_currency='XYZ', help_text=(
          'This is typically negative.'))
  reason = models.TextField()
  when = models.DateTimeField(default=timezone.now)
  rental = models.ForeignKey(
      Rental, on_delete=models.CASCADE, null=False, default=1)

  objects = AdjustmentManager()

  def transaction_on(self):
    return self.when

  def get_owner(self):
    return self.rental.owner
