""" This got complicated enough it gets its own file. Guesty doesn't send ids
along with payment information at this time so this file is largely dedicated
to helpful functions I created to identify and fix duplicates.

OK! A lot of this complexity is due to guesty not including ids with their
payments for a long time. But now they do. So an awful lot of this file can be
replaced by simply referencing the id. """
from datetime import timedelta

from django.utils.dateparse import parse_datetime
from djmoney.money import Money

from reservations.models import Reservation, Payment, Refund, AuthorizationHold
from stripe.models import Charge  # Ugly.
from errors.models import log_error


def sync_payments(reservation, money):
  """ Holy cow I wish these came with ids. Actually I hear they will soon.
  Actually now they do. """
  payment_count = 0
  payments_accounted_for_already = []
  holds_accounted_for_already = []
  refund_accounted_for_already = []
  for p_data in _succeeded_p_datas(money):
    payment_id = p_data.get('_id', None)
    if not payment_id:
      # If we never receive this alert, then we can simplify this file
      # dramatically.
      log_error(
          'Pament merge logic still necessary', 'A payment doesnt have an id.')
    accounted_for_already = None
    currency = _get_currency(p_data)
    is_auth_hold = p_data['isAuthorizationHold']
    PaymentOrHold = None
    if is_auth_hold:
      PaymentOrHold = AuthorizationHold
      accounted_for_already = holds_accounted_for_already
    else:
      PaymentOrHold = Payment
      accounted_for_already = payments_accounted_for_already
      payment_count += 1
    payment_kwargs = get_payment_kwargs(p_data, reservation, currency)
    existing = PaymentOrHold.objects.filter(**payment_kwargs).exclude(
        pk__in=accounted_for_already).first()
    money_taker = None
    if existing:
      money_taker = existing
    else:
      money_taker = PaymentOrHold.objects.create(**payment_kwargs)

    # So here I am grabbing onto the id at least. But all the logic in this
    # file still ignores the id. Soon I shall rip quite a bit nonsense out of
    # here.
    money_taker.channel_manager_id = payment_id
    for attempt in p_data.get('attempts', []):
      if attempt['status'] == 'SUCCEEDED':
        money_taker.payment_provider_id = attempt.get(
            'payload', {}).get('id', None)
    money_taker.save()

    accounted_for_already.append(money_taker.pk)
    if not is_auth_hold:
      # Sometimes auth holds have refunds for some reason. I believe this
      # to be irrelevant to our purposes.
      for refund_data in p_data.get('refunds', []):
        if refund_data['status'] == 'SUCCEEDED':
          amount = Money(refund_data['amount'], currency)
          created_at = parse_datetime(refund_data['createdAt'])
          channel_manager_id = refund_data.get('_id', None)
          payment_provider_id = refund_data.get('payload', {}).get('id', None)

          existing = None
          # Stripe payments come with a payment_provider_id, so Booking.com
          # reservations for instance will have one.
          if channel_manager_id:
            existing = Refund.objects.filter(
                channel_manager_id=channel_manager_id).first()
          else:
            subject = (
                'Not all refunds come with a channel_manager_id')
            log_error(subject, 'Reservation {} has {}'.format(
                reservation.pk, refund_data))
            existing = Refund.objects.filter(
                payment__reservation=reservation, amount=amount).exclude(
                    pk__in=refund_accounted_for_already).first()

          refund = None
          if existing:
            refund = existing
          else:
            refund = Refund.objects.create(
                payment=money_taker, amount=amount, created_at=created_at)

          refund.channel_manager_id = channel_manager_id
          refund.payment_provider_id = payment_provider_id
          refund.created_at = created_at

          refund.save()
          refund_accounted_for_already.append(refund.pk)
  reservation.should_have_payment_count = payment_count
  reservation.save()

  # I don't really care if there are too many authorization holds. We just care
  # if they exist at all. When it comes to payments though, "how much" and "how
  # many" are very important!
  if payment_count != reservation.payment_set.count():
    fix_problems(reservation=reservation, money=money, verbose=False)

  if payment_count != reservation.payment_set.count():
    log_error('Problem syncing payments', (
        'Reservation {} has {} payments in the database but it should '
        'have {}').format(
            reservation.pk, reservation.payment_set.count(), payment_count))


def fix_problems(reservation=None, money=None, verbose=True):
  if bool(reservation) != bool(money):
    raise Exception('Either specify both reservation and money or neither.')
  reservations = None
  if reservation:
    reservations = [reservation]
  else:
    reservations = get_mismatched_payment_reservations()
  fixed = True
  for reservation in reservations:
    fixed_payment_does_not_exist = fix_payment_does_not_exist(
        reservation, money=money)
    fixed_identical = fix_identical_payments(reservation)
    if not (fixed_identical or fixed_payment_does_not_exist):
      if verbose:
        print('Unable to resolve reservation {}'.format(reservation.pk))
      fixed = False
  return fixed


def describe_money(res):
  from guesty.guesty import get_money as guesty_get_money
  money = guesty_get_money(res.guestyreservation.guesty_id)
  for payment in money['payments']:
    if payment['status'].find('SUCCEEDED') >= 0:
      for attempt in payment['attempts']:
        if attempt['status'] == 'SUCCEEDED':
          when = parse_datetime(
              payment.get('paidAt', payment['createdAt'])).date()
          amount = payment['amount']
          print('{} ${}'.format(when, amount))


def get_payment_kwargs(p_data, reservation, currency):
  # Default paidAt to createdAt because I'm not sure when the paidAt field
  # started to be populated.
  payment_kwargs = dict(
      reservation=reservation,
      amount=Money(p_data['amount'], currency),
      paid_at=parse_datetime(p_data.get('paidAt', p_data['createdAt'])))
  for attempt in p_data.get('attempts', []):
    if attempt['status'].find('SUCCEEDED') >= 0:
      source = attempt['payload']['source']
      payment_kwargs['cc_last_4'] = source['last4']
      payment_kwargs['cc_brand'] = source['brand']
  return payment_kwargs


def payment_in_money(payment, money):
  for p_data in _succeeded_p_datas(money):
    kwargs = get_payment_kwargs(
        p_data, payment.reservation, _get_currency(p_data))
    # These are missing for Airbnb payments.
    kwargs['cc_last_4'] = kwargs.get('cc_last_4', None)
    kwargs['cc_brand'] = kwargs.get('cc_brand', None)
    if all([
        payment.cc_last_4 == kwargs['cc_last_4'],
        payment.cc_brand == kwargs['cc_brand'],
        payment.amount == kwargs['amount'],
        payment.paid_at == kwargs['paid_at']]):
      return True
  return False


def identical(pay1, pay2):
  """ Are these payments identical? """
  return all([
      pay1.cc_last_4 == pay2.cc_last_4,
      pay1.cc_brand == pay2.cc_brand,
      pay1.amount == pay2.amount,
      abs(pay1.paid_at - pay2.paid_at) < timedelta(seconds=5)])


def find_identical_payments(reservation):
  for pay1 in reservation.payment_set.order_by('pk'):
    for pay2 in reservation.payment_set.filter(pk__gt=pay1.pk):
      if identical(pay1, pay2):
        return (pay1, pay2)


def fix_payment_does_not_exist(reservation, money=None):
  if not money:
    from guesty.guesty import get_money  # Ugly. Circular dependency.
    money = get_money(reservation.guestyreservation.guesty_id)
  fixed = False
  for payment in reservation.payment_set.all():
    if not payment_in_money(payment, money):
      fixed = delete_payment(payment) or fixed
  return fixed


def delete_payment(payment):
  if get_auth_holds(payment):
    return False
  charge = get_charge(payment)
  if charge:
    charge.payment = None
    charge.save()
    # These will be recreated when the charge is re-attached to a payment.
    payment.creditcardfee_set.all().delete()
  # Refund data is nested inside payment info. So if this payment doesn't exist
  # then the refunds don't either.
  payment.refund_set.all().delete()
  payment.delete()
  if charge:
    charge.match_to_payment()
  return True


def fix_identical_payments(reservation):
  to_return = False
  found = find_identical_payments(reservation)
  while found:
    pay1, pay2 = found
    if not referenced(pay1):
      pay1.delete()
    elif not referenced(pay2):
      pay2.delete()
    else:
      # OK stripe grabbed the duplicates and associated charges with them.
      if delete_payment(pay2):
        to_return = True
      else:
        # Oh, aaaaah, ran into trouble, let's just move on.
        return False
    found = find_identical_payments(reservation)
  return to_return


def get_mismatched_payment_reservations():
  problems = []
  ress = Reservation.objects.filter(
      guestyreservation__isnull=False, should_have_payment_count__gt=0)
  for res in ress:
    if res.payment_set.count() != res.should_have_payment_count:
      problems.append(res)
  return problems


def get_charge(payment):
  return Charge.objects.filter(payment=payment).first()


def get_auth_holds(payment):
  return AuthorizationHold.objects.filter(payment=payment)


def referenced(payment):
  """ Just make sure when we fix identical payments we aren't deleting other
  stuff too. These relationships are in Payment._meta.related_objects """
  return get_auth_holds(payment) or (
      payment.refund_set.all() or (
          payment.creditcardfee_set.all() or (
              get_charge(payment))))


def _succeeded_p_datas(money):
  to_return = []
  for p_data in money['payments']:
    # For payments it's SUCCEEDED, for holds it's AUTHORIZATION_HOLD_SUCCEEDED
    if p_data['status'].find('SUCCEEDED') >= 0:
      to_return.append(p_data)
  return to_return


def _get_currency(p_data):
  return p_data['currency'].upper()


def _is_auth_hold(p_data):
  return p_data['isAuthorizationHold']
