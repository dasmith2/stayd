""" This is just money stuff related to reservations. Even so, this file is
getting a little big!

When it comes to getting paid, there's the IDEAL amount we'd like to get paid,
a.k.a. the sum of the line items. There's the ACTUAL amount we got paid, a.k.a.
the sum of the payments. Finally, there's the LIKELY amount we'll get paid,
which is a bit of a trickier concept. An airbnb reservation with an ideal
payin of $200 and an actual payin of $0 on the day of checkin has a likely
payin of $200 because we'll probably get paid tomorrow or the day after. But if
we still haven't gotten paid a week after checkin, the likely payin drops to
$0.

I used to use the word "expected" payin, but that was a terribly ambiguous and
confusing term because it wasn't clear if I was talking about the IDEAL payin
or the LIKELY payin. """
from collections import namedtuple
from datetime import timedelta
from decimal import Decimal
import json

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.forms import ModelForm
from django.shortcuts import reverse
from djmoney.money import Money
from djmoney.models.fields import MoneyField

from commands.models import background_command
from errors.models import notify
from guests.models import GuestPhoneNumber
from reservations.models.reservation_base import (
    ReservationBase, ReservationManagerBase, CONFIRMED)
from util.channels import (
    THEY_ASSUME_CC_RISK_CHANNELS, THEY_TAKE_SECURITY_DEPOSIT,
    WE_ASSUME_CC_RISK_CHANNELS, PAYMENTS_DONT_SYNC)
from util.fields import OneToOneOrNoneField
from util.signals import post_sync
from util.timezone import now, str_to_tz_dt, tz_dt_to_tz_dt
from util.urls import keys_url


AIRBNB_EXPECT_TO_BE_PAID_DAYS_AFTER_CHECKIN = 4
BOOKINGCOM_EXPECT_TO_BE_PAID_DAYS_BEFORE_CHECKIN = 6
EXPECT_PAYMENT_DATA_PAST = str_to_tz_dt('2018-06-01 00:00')


@background_command
def alert_likely_payin_not_ideal_payin_background():
  problems = Reservation.objects.likely_payin_not_ideal_payin().filter(
      resolution__isnull=True)
  problem_count = problems.count()
  if problem_count:
    subject = 'Reservations that aren\'t paid in good'
    url = keys_url(reverse('unresolved_likely_payin_not_ideal'))
    count_str = 'these {} reservations have serious payment issues'.format(
        problem_count)
    if problem_count == 1:
      count_str = 'this 1 reservation has a serious payment issue'
    message = (
        'Uh... {} that nobody\'s looked at yet.\n\n{}').format(
            count_str, url)
    notify(settings.ALERT_LIKELY_PAYIN_NOT_IDEAL, subject, message)


class KNOWN_LINE_ITEM_NAMES:
  """ I found these with this query on the production database:
  SELECT DISTINCT(name) FROM reservations_reservationlineitem;
  Host channel fee and Airbnb Service Fee are negative.
  As you can see, capitalization is hit and miss. This is because many of these
  are typed in manually!
  """
  def is_channel_fee(self, name):
    return name.lower() in [ty.lower() for ty in self.CHANNEL_FEE_NAMES]

  def is_cleaning(self, name):
    return name.lower() in [ty.lower() for ty in self.CLEANING_NAMES]

  def is_rent(self, name):
    return name.lower() in [ty.lower() for ty in self.RENT_NAMES]

  def is_rent_or_correction(self, name):
    types = self.RENT_NAMES + self.CORRECTION_NAMES
    return name.lower() in [ty.lower() for ty in types]

  def is_tax(self, name):
    return name.lower() in [ty.lower() for ty in [self.CITY_TAX]]

  def is_upsell(self, name):
    return name.lower() in [ty.lower() for ty in [
        self.EARLY_CHECKIN, self.EARLY_CHECKIN_2]]

  CITY_TAX = 'CITY_TAX'

  HOST_CHANNEL_FEE = 'Host channel fee'
  AIRBNB_SERVICE_FEE = 'Airbnb Service Fee'
  CHANNEL_FEE_NAMES = [HOST_CHANNEL_FEE, AIRBNB_SERVICE_FEE]

  RENT = 'Rent'
  ACCOMMODATION_FARE = 'Accommodation fare'
  # These are because of some complicated thing that happened when we ported
  # over to Guesty. Something about, Guesty insisted on calculating tax even
  # though we'd taken tax as a line item, so we had to do some high school
  # algebra to figure out how much of a correction we had to make so Guesty
  # would consider the imported reservations paid in full... something like
  # that.
  GUESTY_CORRECTION = 'Guesty correction'
  RENT_NAMES = [RENT, ACCOMMODATION_FARE, GUESTY_CORRECTION]

  # These happen because Guesty isn't smart enough to handle (I think they're
  # called) "service fees" of 14.5% that we add on Booking.com to compensate
  # for the fees they charge us. So for existing reservations that used that
  # mechanism we had to add corrections to Guesty to make the numbers add up
  # so Guesty will charge the guest exactly what we quoted them.
  CORRECTION = 'correction'
  GUESTY_CORRECTION = 'Guesty correction'
  REFUND = 'Refund'
  CORRECTION_NAMES = [CORRECTION, GUESTY_CORRECTION, REFUND]

  CLEANING_FEES = 'Cleaning Fees'
  CLEANING_FEE = 'Cleaning fee'
  CLEANING_NAMES = [CLEANING_FEES, CLEANING_FEE]

  EARLY_CHECKIN = 'early checkin'
  EARLY_CHECKIN_2 = 'Early Check In'  # I bet these are being entered freehand.


class ReservationManager(ReservationManagerBase):
  def latest_webhook_disagrees_payin(self):
    """ For every guesty reservation, find the latest guesty webhook. See how
    much that webhook says we got paid in, and if that amount is different from
    what we have in our database. This is a way to check how in sync we are
    with guesty. It helped me come up with a list of examples of reservations
    that had received refunds after the last webhook, which allowed me to bug
    Guesty to please send webhooks when refunds happen. """
    Disagree = namedtuple(
        'Disagree', 'reservation db_paid latest_webhook hook_paid')
    for res in self.filter(guestyreservation__isnull=False).order_by(
        '-booked_at'):
      latest = res.rawevent_set.order_by('-created_at').first()
      if latest:
        data = json.loads(latest.json)['reservation']
        hook_paid = data['money']['totalPaid']
        db_paid = float(res._calc_actual_payin().amount)
        if hook_paid != db_paid:
          yield(Disagree(res, db_paid, latest, hook_paid))

  def ensure_ideal_payin_equals_line_items(self):
    """ This doesn't actually get run anywhere at this time, but you can use it
    to reassure yourself that for every reservation in the database, the
    ideal_payin is equal to the sum of the values of the reservation line
    items. Note that channel fee line items are negative. """
    for res in self.all():
      from_field = res.ideal_payin
      from_lis = sum([li.value for li in res.reservationlineitem_set.all()])
      if from_field - from_lis != Money('0', 'USD'):
        yield res

  def no_cc_info(self):
    """ These are reservations where a successful payment was taken, but it was
    taken in such a way that we don't know the last 4 digits of the cc or the
    type of cc used. Now it includes authorization holds that don't include cc
    info in the case of channels where they take payment but we take security
    deposits. In these cases, we can't verify the id. These are hopefully rare
    special cases that must be handled one by one. For example, you might load
    the guesty reservation and just go ahead and flip the id verified switch.
    """
    they_take_payment = models.Q(channel__in=THEY_ASSUME_CC_RISK_CHANNELS)
    we_take_payment = ~they_take_payment
    payment_exists = models.Q(valid_payments_exist=True)
    they_take_security = models.Q(channel__in=THEY_TAKE_SECURITY_DEPOSIT)
    we_take_security = they_take_payment & ~they_take_security
    authorization_exists = models.Q(maximum_authorization_hold__isnull=False)
    return self.filter(
        (we_take_payment & payment_exists) | (
            we_take_security & authorization_exists),
        cc_last_4__isnull=True,
        status=CONFIRMED, check_out__gt=now(),
        guestyreservation__isnull=False, id_verified=False).order_by(
        'check_in')

  def cc_action_required(self):
    """ These are reservations where we have to take the payment, but no
    payment has been taken successfully yet. If payments are scheduled to be
    taken, then the first attempt came and went already. Reservations end up in
    this list if a guest types in their CC info wrong, for instance. Now this
    list includes reservations where the channel takes payments, but we take a
    security deposit, and no authorization hold exists yet so we can't verify
    an id yet or be assured that we can successfully take a security deposit.
    """
    they_take_payment = models.Q(channel__in=THEY_ASSUME_CC_RISK_CHANNELS)
    we_take_payment = ~they_take_payment
    past_first_scheduled_payment = (
        models.Q(first_payment_scheduled_on__isnull=True) | models.Q(
            first_payment_scheduled_on__lt=now() - timedelta(minutes=90)))
    payment_missing = past_first_scheduled_payment & models.Q(
        valid_payments_exist=False)
    payment_problem = we_take_payment & payment_missing
    they_take_security = models.Q(channel__in=THEY_TAKE_SECURITY_DEPOSIT)
    we_take_security = they_take_payment & ~they_take_security
    authorization_missing = models.Q(maximum_authorization_hold__isnull=True)
    security_problem = we_take_security & authorization_missing
    problems = payment_problem | security_problem
    return self.filter(
        problems, status=CONFIRMED, check_out__gt=now(),
        guestyreservation__isnull=False).order_by(
        'check_in')

  def expecting_payments(self):
    not_synced_recently = models.Q(
        last_synced_at__lte=now() - timedelta(hours=1)) | models.Q(
            last_synced_at__isnull=True)
    should_have_been_paid_recently = models.Q(
        check_in__gte=now() - timedelta(
            days=AIRBNB_EXPECT_TO_BE_PAID_DAYS_AFTER_CHECKIN))

    # For example we typically get word of Airbnb payouts, oh, 4 or 5 days
    # after check in. Booking.com reservations get multiple payments, so don't
    # do a filter like payment__isnull=False. Again this is all because Guesty
    # still doesn't send us a webhook when a successful payment arrives so we
    # gotta check for ourselves. This applies to confirmed and canceled
    # reservations and reservations in (almost) every channel.
    for reservation in Reservation.objects.filter(
        not_synced_recently,
        should_have_been_paid_recently,
        guestyreservation__isnull=False):
      if reservation.get_balance_due():
        yield reservation

  def likely_payin_not_ideal_payin(self, nnow=None):
    """ If this were actual_payin_not_ideal_payin, this would be a) much
    simpler and b) much less helpful. The actual payin is just how much money
    we received so far and the ideal is how much we billed for. It's often
    expected that the actual payin is not yet the ideal payin. Where we get
    worried is when the LIKELY payin is not the ideal payin, and the LIKELY
    payin takes into account all kinds of things like what channel this is on
    and that channels payout schedule. """
    # Is it even possible to know how much we got paid?
    nnow = nnow or now()
    not_old_airbnb = ~Q(
        channel__in=THEY_ASSUME_CC_RISK_CHANNELS,
        check_out__lte=EXPECT_PAYMENT_DATA_PAST)
    not_test_reservation = Q(
        is_test_reservation=False,
        rental__is_test_rental=False)
    in_guesty = Q(guestyreservation__isnull=False)
    # If this reservation was imported after checkin, we probably just took
    # over somebody's existing airbnb account.
    imported_before_checkin = Q(imported_at__isnull=True) | Q(
        imported_at__lt=F('check_in'))
    # Unfortunately, there are a few channels who don't sync their payment
    # information with Guesty.
    channel_syncs_to_guesty = ~Q(channel__in=PAYMENTS_DONT_SYNC)
    possible_to_know_payments = Q(
        not_old_airbnb, not_test_reservation, in_guesty,
        channel_syncs_to_guesty, imported_before_checkin)

    # It's always a mistake to get paid more than the bill.
    paid_too_much = Q(actual_payin__gt=F('ideal_payin'))
    # If we didn't get paid enough, it's only a problem if we were supposed to
    # get paid by now.
    paid_by_now_airbnb = Q(
        channel__in=THEY_ASSUME_CC_RISK_CHANNELS,
        check_in__lt=nnow - timedelta(
            days=AIRBNB_EXPECT_TO_BE_PAID_DAYS_AFTER_CHECKIN))
    paid_by_now_bookingcom = Q(
        channel__in=WE_ASSUME_CC_RISK_CHANNELS,
        check_in__lt=nnow + timedelta(
            days=BOOKINGCOM_EXPECT_TO_BE_PAID_DAYS_BEFORE_CHECKIN))
    paid_by_now = paid_by_now_airbnb | paid_by_now_bookingcom
    paid_lt_ideal = Q(actual_payin__lt=F('ideal_payin')) | Q(
        actual_payin__isnull=True, ideal_payin__gt=0)
    paid_too_little = Q(paid_by_now, paid_lt_ideal)

    paid_wrong = paid_too_much | paid_too_little
    return Reservation.objects.filter(possible_to_know_payments, paid_wrong)


class Reservation(ReservationBase):
  ideal_payin = MoneyField(
      max_digits=10, decimal_places=2, default_currency='XYZ', help_text=(
          'Total amount that SHOULD IDEALLY land in our bank account due to '
          'this reservation. It\'s not revenue, exactly, because it reflects '
          'things like Airbnb\'s service fee which comes out of our hides. '
          'Airbnb calls this total_payout for obvious reasons. This comes '
          'from the hostPayout field in Guesty.'))
  actual_payin = MoneyField(
      max_digits=10, decimal_places=2, default_currency='XYZ', null=True,
      blank=True, help_text=(
          'The difference from ideal_payin is that this is calculated '
          'from the sum of the payments and refunds post-sync. Ideally '
          'theyre the same! But they often arent.'))
  credit_card_fees_calculated = MoneyField(
      max_digits=10, decimal_places=2, default_currency='XYZ', null=True,
      blank=True, help_text=(
          'This is calculated from the sum of the credit card fees.'))
  valid_payments_exist = models.BooleanField(default=False, help_text=(
      'Were there ANY valid payments made against this reservation? '
      'This only really matters on channels where we assume the payment '
      'risk.'))
  maximum_authorization_hold = MoneyField(
      max_digits=10, decimal_places=2, default_currency='XYZ', null=True,
      blank=True, help_text=(
          'The amount of the hold placed on a credit card for this '
          'reservation.'))
  first_payment_scheduled_on = models.DateTimeField(
      null=True, blank=True, help_text=(
          'Dont show Booking.com reservations in the "Credit card action '
          'required" tab until the first auto payment has a chance to run.'))

  # These are normalized with payments. Not a huge fan of that. This cc_last_4
  # is getting populated in guesty.py while the payment cc_last_4 is getting
  # set in sync_payments.py
  cc_last_4 = models.CharField(
      max_length=4, null=True, blank=True, db_index=True, help_text=(
          'We only get the last 4 digits of the cc on channels where we '
          'assume the payment risk, such as Booking.com, AND where a '
          'successful payment occured. This field gets compared to a picture '
          'of the guests credit card by an admin as part of the id '
          'verifcation flow.'))
  cc_brand = models.CharField(
      max_length=20, null=True, blank=True, db_index=True, help_text=(
          'Same story as cc_last_4.'))

  should_have_payment_count = models.PositiveIntegerField(
      null=True, blank=True, help_text=(
          'Guesty doesnt give payments IDs so there are issues with '
          'duplicates and such. Having this hear simplifies finding the '
          'problems.'))

  objects = ReservationManager()

  def when_cc_action_required(self):
    """ Let's say there was a credit card issue with this reservation. When
    would we start wanting to resolve it? """
    first = self.first_payment_scheduled_on
    created = self.created_at
    if first and created:
      first += timedelta(minutes=90)
      return tz_dt_to_tz_dt(max([created, first]))

  def attributed_to_rental(self, rental):
    """ What fraction of this reservation ought to be attributed to the given
    rental? """
    if rental == self.rental:
      return 1.0
    rentals = self.rental.get_rentals()
    if rental not in rentals:
      raise Exception(
          'Reservation {} has nothing to do with rental {}'.format(
              self.pk, rental.pk))
    total_capacity = sum([atom.accommodates for atom in rentals])
    return rental.accommodates / total_capacity

  def has_resolution(self):
    try:
      return bool(self.resolution)
    except Reservation.resolution.RelatedObjectDoesNotExist:
      return False

  def get_balance_due(self):
    # get_actual_payin will log_error if it returns None.
    gotten_payin = self.get_actual_payin()
    if gotten_payin is None:
      return self.ideal_payin
    return self.ideal_payin - gotten_payin

  def get_likely_balance_due(self, nnow=None):
    return self.ideal_payin - self.get_likely_payin(nnow)

  def is_paid_in(self):
    # Sometimes things go wrong and guests overpay, so balance due could be
    # negative.
    return self.get_balance_due().amount <= Decimal('0.01')

  def we_need_to_collect_more_money(self):
    our_cc_risk = self.channel not in THEY_ASSUME_CC_RISK_CHANNELS
    # I have in my head that Guesty doesn't allow us to collect payments of
    # less than 1 dollar, and sometimes we're owed, like, 4 cents.
    has_collectable_balance = self.get_balance_due().amount > Decimal('1')
    return our_cc_risk and has_collectable_balance

  def has_security_deposit(self):
    """ Authorization holds do double duty. For OnlyApartments, we take a $1
    authorization hold so we know we've got a valid CC and that information
    propegates through the system so we can ask "Is this a cc with last 4
    digits 1234?" in ID verification. That's not a valid security deposit
    though, which is of course the other use for authorization holds. """
    if not self.maximum_authorization_hold:
      return False
    cutoff = Money(
        settings.MINIMUM_SECURITY_DEPOSIT,
        self.maximum_authorization_hold.currency)
    return self.maximum_authorization_hold and (
        self.maximum_authorization_hold > cutoff)

  def prepayment(self):
    """ For Booking.com reservations this is the payment we take at the time of
    booking. """
    if self.channel in WE_ASSUME_CC_RISK_CHANNELS:
      return self.payment_set.order_by('paid_at').first()

  def cc_action_required(self):
    return Reservation.objects.cc_action_required().filter(pk=self.pk).exists()

  def line_items(self):
    return self.reservationlineitem_set.all()

  def we_assume_cc_risk(self):
    return self.channel not in THEY_ASSUME_CC_RISK_CHANNELS

  def we_take_security_deposit(self):
    return self.channel not in THEY_TAKE_SECURITY_DEPOSIT

  def explain_cc_action_required(self):
    if self.we_assume_cc_risk():
      if not self.valid_payments_exist:
        return '{} reservations require an initial payment.'.format(
            self.channel)
    elif self.we_take_security_deposit() and (
        not self.maximum_authorization_hold):
      return '{} reservations require a $1 authorization'.format(self.channel)

  def get_actual_payin(self, nnow=None):
    """ How much did we actually get paid? This returns 0 for future
    reservations because we didn't get paid yet. """
    nnow = nnow or now()
    zero = Money('0', self.rental.building.currency)
    # Test reservations have no income.
    if self.get_is_test_reservation():
      return zero
    # We've got a cached value calculated from payments. Best case scenario.
    if self.actual_payin:
      return self.actual_payin
    # We got payments. Great. Let's use those. This caches it in actual_payin
    # btw.
    if self.payment_set.exists():
      return self._calc_actual_payin()
    # For canceled reservations, the only way we know if we got cancelation
    # fees is from the payments. So if there aren't any payments and it's
    # canceled, most likely scenario is we never got paid. But this assumption
    # almost certainly means we're missing some cancelation fees from 2018.
    # We'll be ok.
    if self.canceled():
      return zero
    # Old reservations may lack payment information. We dug into this. It
    # wasn't super clear what was happening, but it was something like, if we
    # imported the reservation and the check out was a month previous then our
    # channel manager was unable to get the retroactive payment info from
    # Airbnb. So if the channel handles the payments and the reservation is
    # confirmed and it's old, safest bet is that we got paid the
    # ideal_payin.
    if self.channel in THEY_ASSUME_CC_RISK_CHANNELS and (
        self.check_in < EXPECT_PAYMENT_DATA_PAST):
      return self.ideal_payin
    if self.imported_at:
      # OK you know that last check we did? Well it's not sophisticated enough.
      # When we onboard new units, we may get more recent reservations imported
      # long enough after the reservation that we can't expect payment
      # information.
      imported_more_than_a_week_after_checkin = (
          self.check_in + timedelta(days=7) < self.imported_at)
      if imported_more_than_a_week_after_checkin:
        return self.ideal_payin
    # We don't get paid until a few days after check_in.
    if nnow <= self._expect_to_be_paid_at():
      return zero
    # Guesty is too dumb to recognize when we get paid for these reservations.
    # So we just assume we did get paid and accept that we'll probably assume
    # we got paid when we didn't for a reservation at some point.
    if self.channel in PAYMENTS_DONT_SYNC:
      return self.ideal_payin
    # If this reservation was imported directly into our database without a
    # channel manager then we'll just have to take our word for it.
    if not self.get_syncer():
      return self.ideal_payin
    # Having considered all the things, I have no choice but to admit we
    # probably got paid nothing.
    return zero

  def get_likely_payin(self, nnow=None):
    """ The amount, given the information we have, that we suspect will be paid
    in for this reservation. It depends on time because it depends on when we
    ideally were going to get paid. If we thought we were going to get paid a
    month ago and we never did, then the likely payin drops to the actual
    payin, perhaps of 0. But if we won't be ideally paid for a month still,
    then the likely payin is equal to the ideal_payin. """
    nnow = nnow or now()
    if nnow < self._expect_to_be_paid_at():
      # I assume the best of people. We don't expect to be paid in yet.  Odds
      # are good we will get paid though.
      return self.ideal_payin
    return self.get_actual_payin()

  def _expect_to_be_paid_at(self):
    if self.channel in WE_ASSUME_CC_RISK_CHANNELS:
      return self.check_in - timedelta(
          days=BOOKINGCOM_EXPECT_TO_BE_PAID_DAYS_BEFORE_CHECKIN)
    return self.check_in + timedelta(
        days=AIRBNB_EXPECT_TO_BE_PAID_DAYS_AFTER_CHECKIN)

  def _calc_actual_payin(self):
    got = Money('0', self.rental.building.currency)
    payments = self.payment_set.all()
    if payments:
      got = sum([pay.get_actual_amount() for pay in payments])
    if self.actual_payin != got:
      self.actual_payin = got
      self.save()
    return got

  def _calc_ideal_payin(self):
    got = Money('0', self.rental.building.currency)
    line_items = self.reservationlineitem_set.all()
    if line_items:
      got = sum([line_item.value for line_item in line_items])
    if self.ideal_payin != got:
      self.ideal_payin = got
      self.save()
    return got

  def get_credit_card_fees(self):
    if self.credit_card_fees_calculated is None:
      return self._calc_cc_fees()
    return self.credit_card_fees_calculated

  def _calc_cc_fees(self):
    got = Money('0', self.rental.building.currency)
    for cc_fee in CreditCardFee.objects.filter(payment__reservation=self):
      got += cc_fee.amount
    self.credit_card_fees_calculated = got
    self.save()
    return got

  @receiver(pre_save)
  def pre_save(sender, instance, *args, **kwargs):
    """ This is ugly. For starters, it doesn't run during, say,
    Reservation.objects.filter(whatever).update(whatever). But timezones
    and currencies are REALLY ugly, using all kinds of defaults and
    assumptions, or not using as the case may be. The moral of the story
    is, we gotta be careful with those. """
    if instance.__class__ is Reservation:
      rental = instance.rental
      instance.check_in = rental.building.set_timezone(instance.check_in)
      instance.check_out = rental.building.set_timezone(instance.check_out)
      instance.ideal_payin = rental.building.set_currency(
          instance.ideal_payin)


@receiver(post_sync, sender=Reservation)
def post_reservation_sync(sender, instance, *args, **kwargs):
  instance.last_synced_at = now()
  instance._calc_actual_payin()
  instance._calc_cc_fees()
  instance._calc_ideal_payin()
  instance.save()


class MoneyTaker(models.Model):
  reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE)
  cc_last_4 = models.CharField(
      max_length=4, null=True, blank=True, db_index=True)
  cc_brand = models.CharField(max_length=20, null=True, blank=True)
  amount = MoneyField(
      max_digits=10, decimal_places=2, default_currency='USD', db_index=True)
  paid_at = models.DateTimeField(default=str_to_tz_dt('2018-01-01 00:00'))
  channel_manager_id = models.CharField(
      max_length=200, null=True, blank=True, help_text=(
          'An ID assigned to this payment by whatever data source we got it '
          'from.'))
  payment_provider_id = models.CharField(
      max_length=200, null=True, blank=True,
      help_text='For example, the Stripe id.')

  class Meta:
    abstract = True


class Payment(MoneyTaker):
  def has_refunds(self):
    return self.refund_set.exists()

  def get_refund_amount(self):
    refunds = self.refund_set.all()
    if refunds:
      return sum([refund.amount for refund in refunds])
    return Money('0', self.reservation.rental.building.currency)

  def get_actual_amount(self):
    return self.amount - self.get_refund_amount()

  def __repr__(self):
    return '<Payment {}: {} ${}>'.format(
        self.pk, self.paid_at.date(), self.amount.amount)


class AuthorizationHold(MoneyTaker):
  payment = OneToOneOrNoneField(
      Payment, on_delete=models.CASCADE, blank=True, null=True, help_text=(
          'When we cash in an authorization hold it causes a payment.'))


class Refund(models.Model):
  """ Not to be confused with Stripe refunds. I mean, some of these are
  basically stripe refunds but many of them are Airbnb refunds or whatever. """
  created_at = models.DateTimeField()
  payment = models.ForeignKey(Payment, on_delete=models.CASCADE)
  amount = MoneyField(
      max_digits=10, decimal_places=2, default_currency='USD', help_text=(
          'These come in as positive numbers.'))
  channel_manager_id = models.CharField(
      max_length=200, null=True, blank=True,
      help_text='For example, the guesty id.')
  payment_provider_id = models.CharField(
      max_length=200, null=True, blank=True,
      help_text='For example, the Stripe id.')

  def __repr__(self):
    return '<Refund {}: {} {}>'.format(
        self.pk, self.created_at.date(), self.amount)


class CreditCardFee(models.Model):
  payment = models.ForeignKey(Payment, on_delete=models.CASCADE)
  description = models.TextField()
  amount = MoneyField(
      max_digits=10, decimal_places=2, default_currency='USD')


class ReservationLineItem(models.Model):
  """ Line items that add up to a reservation's ideal_payin. For instance,
  there could be Rent, the Airbnb service fee which will be negative, and a
  cleaning charge. """
  name = models.TextField(help_text=(
      'I don\'t know for sure what these can be, but see '
      'KNOWN_LINE_ITEM_NAMES for what I\'ve seen so far.'))
  # Gah, this should be called amount.
  value = MoneyField(
      max_digits=10, decimal_places=2, default_currency='XYZ')
  reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE)

  def __repr__(self):
    return 'ReservationLineItem({}) {} {}'.format(
        self.pk, self.name, self.value)


class ResolutionCategory(models.Model):
  """ Why is the LIKELY payin different from the IDEAL payin? Note that we
  don't need to resolve reservations whose ACTUAL payin is different from the
  IDEAL payin necessarily because we may be expecting a payin in the future.
  It's only when the LIKELY payin diverges from the IDEAL payin that we get
  worried. """
  name = models.CharField(max_length=200, primary_key=True)

  def __str__(self):
    return self.name


class Resolution(models.Model):
  """ A description of why we feel a reservation is likely to pay in an amount
  that's different from the ideal payin and will probably never get fixed. """
  reservation = OneToOneOrNoneField(Reservation, on_delete=models.CASCADE)
  resolution_category = models.ForeignKey(
      ResolutionCategory, on_delete=models.PROTECT)
  notes = models.TextField(blank=True, null=True)
  ideal_payin = MoneyField(
      max_digits=10, decimal_places=2, default_currency='USD', help_text=(
          'When this reservation was marked resolved, what was the '
          'amount we SHOULD have gotten paid? Keep track of this in case it '
          'changes, in which case the resolution would need to be revisited.'))
  actual_payin = MoneyField(
      max_digits=10, decimal_places=2, default_currency='USD', help_text=(
          'When this reservation was marked resolved, what was the '
          'amount we ACTUALLY got paid? Keep track of this in case it '
          'changes, in which case the resolution would need to be revisited.'))


class ResolutionForm(ModelForm):
  class Meta:
    model = Resolution
    fields = ['resolution_category', 'notes']


def handle_resolve_payin_post(request_post, reservation):
  resolution_form = ResolutionForm(request_post)
  if resolution_form.is_valid():
    resolution_category = resolution_form.cleaned_data['resolution_category']
    notes = resolution_form.cleaned_data['notes']
    Resolution.objects.create(
        reservation=reservation, resolution_category=resolution_category,
        notes=notes, ideal_payin=reservation.ideal_payin,
        actual_payin=reservation.get_actual_payin())
    return True


def get_reservation_from_query(request_GET):
  """ See also verify_id_url_no_server in reservations.models.Reservation """
  name = request_GET.get('name', '')
  guest_first = request_GET.get('guest_first', '')
  phone = request_GET.get('phone', '')
  channel_id = request_GET.get('id', '')
  channel = request_GET.get('channel', '')
  reservations = Reservation.objects.filter(
      check_out__gt=now(), status=CONFIRMED).order_by('check_in')
  if name:
    reservations = reservations.filter(guest__full_name=name)
  if phone:
    guests = GuestPhoneNumber.objects.find_guests(phone)
    reservations = reservations.filter(guest__in=guests)
  if channel_id:
    reservations = reservations.filter(channel_id=channel_id)
  if guest_first:
    reservations = reservations.filter(guest__first_name=guest_first)
  if channel:
    reservations = reservations.filter(channel__iexact=channel)

  how_many = reservations.count()

  none_found = how_many == 0
  only_one = how_many == 1  # Whew, easy.
  # Well, this assumption isn't great, but I guess it's better than nothing.
  # Phone is fairly uniquely identifying.
  more_than_one_but_phone = how_many > 1 and phone
  could_be_anybody = how_many > 1 and not phone

  if none_found or could_be_anybody:
    return None
  elif only_one or more_than_one_but_phone:
    return reservations.first()
