from abc import abstractmethod
from datetime import timedelta, date

from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver
from djmoney.money import Money
from djmoney.models.fields import MoneyField
from django.utils import timezone

from guests.models import Guest
from listings.models import Listing
from pays.models import Payin, Payout, PaypalPayout
from rentals.models import PayoutRule
from util.channels import AIRBNB


class PayoutCalculator(object):
  def assign_adjustments(self):
    # Assign the biggest (a.k.a. most negative) adjustments first because
    # they're the hardest to find a home for. I can see this being a
    # performance issue if we get a ton of these and we're digging through
    # this big table with big joins and an ever increasing backlog of useless
    # adjustments that will never find a home. But I won't prematurely
    # optimize.
    adjustments = ReservationAdjustment.objects.filter(
        payout=None, listing__rental__owner__isnull=False).order_by('amount')
    for adjustment in adjustments:
      owner = adjustment.listing.rental.owner
      payout_rule = adjustment.get_applicable_payout_rule()
      if payout_rule:
        adjust_amount = payout_rule.percent * adjustment.amount
        # At first we're just going to let these payouts sit around on
        # hold, so we'll have some old unsent payouts sitting around
        # probably forever.
        possible_payouts = Payout.objects.filter(
            who_to_pay=owner, when_did=None, when_should__gt=timezone.now())
        for payout in possible_payouts:
          breathing_room = payout.amount + adjust_amount
          if breathing_room >= Money(0, 'USD'):
            adjustment.payout = payout
            adjustment.save()
            payout.amount += adjust_amount
            payout.save()

  def calculate_amount_and_save(self, payout):
    if payout.paid_out_already():
      raise Exception(
          'You can\'t update the amount on a payout that already happened.')
    reservations = Reservation.objects.filter(payout=payout)
    adjustments = ReservationAdjustment.objects.filter(payout=payout)
    amount = Money(0, 'USD')
    owner = None
    payout_rule = None
    for reservation in reservations:
      reservation_owner = reservation.listing.rental.owner
      if not owner:
        owner = reservation_owner
        payout_rule = reservation.get_applicable_payout_rule()
      elif reservation_owner.id != owner.id:
        raise Exception(
            'You can\'t have more than one owner in a payout. {} vs {}'.format(
                reservation_owner.id, owner.id))
      amount += payout_rule.percent * reservation.total_payin
    for adjustment in adjustments:
      amount += payout_rule.percent * adjustment.amount
    payout.amount = amount
    payout.save()


class Payoutable(models.Model):
  listing = models.ForeignKey(Listing, on_delete=models.CASCADE, null=False)
  payout = models.ForeignKey(
      Payout, on_delete=models.CASCADE, null=True, help_text=(
          'The payout that this is reflected on.'))

  @abstractmethod
  def transaction_on(self):
    raise NotImplementedError('transaction_on')

  def get_applicable_payout_rule(self):
    owner = self.listing.rental.owner
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
    owner = self.listing.rental.owner
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


class Reservation(Payoutable):
  channel_reservation_id = models.CharField(
      db_index=True, max_length=50, help_text=(
          'The id given to this reservation by Airbnb, booking.com, '
          'or whomever.'))
  guest = models.ForeignKey(Guest, on_delete=models.CASCADE)
  check_in = models.DateTimeField()
  check_out = models.DateTimeField()
  reservation_created = models.DateTimeField(default=timezone.now)
  # Default currency is useless. It will use XYZ if you don't specify.
  price_per_night = MoneyField(
      max_digits=10, decimal_places=2, default_currency='XYZ')
  night_count = models.PositiveIntegerField(help_text=(
      'How many nights did they stay? We could calculate this from check_in '
      'and check_out, but humor me. This will make reports easier to write.'))
  # Default currency is useless. It will use XYZ if you don't specify.
  total_payin = MoneyField(
      max_digits=10, decimal_places=2, default_currency='XYZ', help_text=(
          'Total amount that landed in our bank account due to this '
          'reservation. It\'s not cost, excactly, because it reflects things '
          'like Airbnb\'s service fee which comes out of our hides. Airbnb '
          'calls this total_payout for obvious reasons.'))
  is_paid_in = models.BooleanField(default=False, help_text=(
      'Whether or not this reservation is in the Airbnb list of '
      'transactions, a.k.a. mama got paid.'))
  status = models.CharField(max_length=100, null=True, help_text=(
      'At the moment this is simply copied directly from the guesty api. '
      '\'confirmed\' is the good one, basically.'))

  def transaction_on(self):
    return self.when_did_we_get_paid()

  def when_did_we_get_paid(self):
    if not self.is_paid_in:
      return
    channel = self.listing.channel
    if channel == AIRBNB:
      return self.check_in + timedelta(days=1)
    else:
      raise Exception(
          'when_did_we_get_paid isn\'t implemented for {} yet'.format(channel))

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
    PayoutCalculator().calculate_amount_and_save(payout)

  def explain_why_no_payout(self):
    if self.payout:
      return
    if not self.when_did_we_get_paid():
      return 'We didn\'t get paid yet.'
    return super(Reservation, self).explain_why_no_payout()

  def _get_payout(self):
    if self.payout:
      return self.payout
    if not self.when_did_we_get_paid():
      return
    payout_rule = self.get_applicable_payout_rule()
    if not payout_rule:
      return
    pay_after_days = timedelta(payout_rule.days_after_payment)
    ideally_payout_on = (self.when_did_we_get_paid() + pay_after_days).date()
    payout_on = max(ideally_payout_on, date.today())
    payouts = Payout.objects.filter(
        who_to_pay=self.listing.rental.owner, when_should=payout_on,
        when_did=None)
    if payouts:
      payout = payouts[0]
    else:
      payout = PaypalPayout.objects.create(
          who_to_pay=self.listing.rental.owner, amount=Money(0, 'USD'),
          when_should=payout_on,
          when_did=None)
    self.payout = payout
    self.save()
    return payout

  def channel_listing_id(self):
    """ The ReservationSerializer ends up serializing a reservation in two
    places. We make it serialize a reservation in the scraper so we can send
    it to the api, but then the api itself loads the just-saved reservation and
    serializes it to return to the scraper. The serializer expects a
    channel_listing_id property or function in both cases. The scraper just
    sets it manually, but we need this function for the other case. """
    return self.listing and self.listing.channel_listing_id

  def line_items(self):
    """ This, like channel_listing_id(), is mainly for the benefit of the
    serializer. But it's kind of handy so it gets used in tests too.
    """
    return ReservationLineItem.objects.filter(reservation=self)

  @receiver(pre_save)
  def pre_save(sender, instance, *args, **kwargs):
    """ This is ugly. For starters, it doesn't run during, say,
    Reservation.objects.filter(whatever).update(whatever). But timezones
    and currencies are REALLY ugly, using all kinds of defaults and
    assumptions, or not using as the case may be. The moral of the story
    is, we gotta be careful with those. """
    if instance.__class__ is Reservation:
      rental = instance.listing.rental
      instance.check_in = rental.set_timezone(instance.check_in)
      instance.check_out = rental.set_timezone(instance.check_out)
      instance.price_per_night = rental.set_currency(instance.price_per_night)
      instance.total_payin = rental.set_currency(instance.total_payin)


class ReservationLineItem(models.Model):
  """ Line items that add up to a reservation's total_payin. For instance,
  there could be Rent which is price_per_night * night_count, the Airbnb
  service fee which will be negative, and a cleaning charge. """
  name = models.TextField()
  # Default currency is useless. It will use XYZ if you don't specify.
  value = MoneyField(
      max_digits=10, decimal_places=2, default_currency='XYZ')
  reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE)


class ReservationToPayin(models.Model):
  """ You can receive multiple payins for the same reservation. You can also
  get paid for multiple reservations on the same payin. I've never seen it
  where you have two reservations, each related to two payins, but I wouldn't
  be surprised.
  """
  reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE)
  payin = models.ForeignKey(Payin, on_delete=models.CASCADE)


class ReservationAdjustment(Payoutable):
  """ We pay out Louie on Thursday, but then find out Friday there was an
  issue and Airbnb took a refund back. This is typically due to a
  particular reservation because they're refunding a particular guest, BUT
  Airbnb only tells you the listing for some reason. Since these are, like,
  clawback adjustments, they get tacked onto payments whose value is greater
  than the adjustment (well, technically, -1 * the adjustment). """
  amount = MoneyField(max_digits=10, decimal_places=2, default_currency='XYZ')
  reason = models.TextField()
  when = models.DateTimeField(default=timezone.now)

  def transaction_on(self):
    return self.when
