from datetime import datetime, timedelta
from decimal import Decimal
import random
import string

from django.utils.timezone import make_aware
from djmoney.money import Money

from guests.tests import get_test_guest
from rentals.tests import get_test_rental
from reservations.models import (
    Reservation, Payment, Refund, CreditCardFee, CONFIRMED, CANCELED,
    ReservationLineItem, KNOWN_LINE_ITEM_NAMES)
from reservations.models.money import (
    ResolutionCategory, Resolution, handle_resolve_payin_post,
    get_reservation_from_query)
from util.channels import BOOKINGCOM, AIRBNB, ONLY_APARTMENTS
from util.random_string import random_string
from util.signals import post_sync
from util.tests import TestCase
from util.timezone import parse_dt, str_to_tz_dt, now


def get_test_reservation_line_item(**kwargs):
  reservation = kwargs.get('reservation', None)
  if not reservation:
    reservation = get_test_reservation(**kwargs)
  line_item = ReservationLineItem.objects.create(
      name=kwargs.get('name', 'Stuff'),
      value=kwargs.get('value', Money('22.77', 'USD')),
      reservation=reservation)
  post_sync.send(sender=Reservation, instance=reservation)
  return line_item


def get_test_reservation(**kwargs):
  check_in = parse_dt(
      kwargs.get('check_in', make_aware(datetime(2018, 5, 26, 15))))
  check_out = parse_dt(
      kwargs.get('check_out', make_aware(datetime(2018, 5, 28, 11))))
  booked_at = parse_dt(kwargs.get('booked_at', check_in - timedelta(days=1)))

  guest = get_test_guest(**kwargs)
  rental = kwargs.get('rental', None)
  if not rental:
    rental = get_test_rental(**kwargs)
  random_channel_id = ''.join(
      random.choice(string.ascii_uppercase + string.digits) for _ in range(7))

  ideal_payin = kwargs.get('ideal_payin', Money(0, 'USD'))
  room_line_item = None
  if 'room_line_item' in kwargs:
    room_line_item = kwargs['room_line_item']
    if isinstance(room_line_item, float) or isinstance(
        room_line_item, Decimal):
      room_line_item = Money(room_line_item, 'USD')
    if ideal_payin == Money(0, 'USD'):
      ideal_payin = room_line_item
  anonymized_email = '{}@airbnb.com'.format(random_string())
  reservation = Reservation(
      channel_id=kwargs.get('channel_id', random_channel_id),
      guest=kwargs.get('guest', guest),
      anonymized_email=kwargs.get('anonymized_email', anonymized_email),
      check_in=check_in,
      check_out=check_out,
      check_out_set_at=kwargs.get('check_out_set_at', booked_at),
      booked_at=booked_at,
      canceled_at=kwargs.get('canceled_at', None),
      planned_arrival=kwargs.get('planned_arrival', None),
      id_verified=kwargs.get('id_verified', False),
      rental=rental,
      channel=kwargs.get('channel', AIRBNB),
      guest_count=kwargs.get('guest_count', 2),
      # This should be the sum of the values of the reservationlineitems
      # otherwise stats.computer pitches a fit.
      ideal_payin=ideal_payin,
      actual_payin=kwargs.get('actual_payin', None),
      valid_payments_exist=kwargs.get('valid_payments_exist', True),
      maximum_authorization_hold=kwargs.get(
          'maximum_authorization_hold', None),
      first_payment_scheduled_on=kwargs.get(
          'first_payment_scheduled_on', None),
      status=kwargs.get('status', CONFIRMED),
      cc_last_4=kwargs.get('cc_last_4', None),
      cc_brand=kwargs.get('cc_brand', None),
      issues=kwargs.get('issues', ''),
      last_synced_at=kwargs.get('last_synced_at', None),
      is_test_reservation=kwargs.get('is_test_reservation', False),
      should_have_payment_count=kwargs.get('should_have_payment_count', None),
      imported_at=kwargs.get('imported_at', None))
  if reservation.check_in > reservation.check_out:
    raise Exception('The check_out should be after the check_in')
  reservation.save()

  # Here I just want the reservation to come from SOMEWHERE so it has a syncer.
  # This is important for, say, get_actual_payin which will simply return the
  # ideal_payin if there is no syncer.
  guesty_id = kwargs.get('guesty_id', random_string(10))
  if guesty_id:  # You can specify guesty_id=None if you actually want that.
    from guesty.models import GuestyReservation
    GuestyReservation.objects.create(
        reservation=reservation,
        guesty_id=guesty_id)

  if room_line_item:
    # These fire off a post_sync.
    get_test_reservation_line_item(
        reservation=reservation, value=room_line_item,
        name=KNOWN_LINE_ITEM_NAMES.RENT)
  if 'last_synced_at' in kwargs:
    reservation.last_synced_at = kwargs['last_synced_at']
    reservation.save()
  return reservation


def get_test_payment(**kwargs):
  reservation = kwargs.get('reservation', None)
  if not reservation:
    reservation = get_test_reservation(**kwargs)
  payment = Payment.objects.create(
      reservation=reservation,
      cc_last_4=kwargs.get('cc_last_4', '1234'),
      cc_brand=kwargs.get('cc_brand', 'Visa'),
      amount=kwargs.get('amount', Money('10.0', 'USD')),
      paid_at=kwargs.get('paid_at', str_to_tz_dt('2018-01-01 00:00')),
      channel_manager_id=kwargs.get('channel_manager_id', None),
      payment_provider_id=kwargs.get('payment_provider_id', None))
  post_sync.send(sender=Reservation, instance=reservation)
  return payment


def get_test_refund(**kwargs):
  payment = kwargs.get('payment', None)
  if not payment:
    payment = get_test_payment(**kwargs)
  refund = Refund.objects.create(
      payment=kwargs.get('payment', payment),
      amount=kwargs.get('amount', Money('10.0', 'USD')),
      channel_manager_id=kwargs.get('channel_manager_id', None),
      payment_provider_id=kwargs.get('payment_provider_id', None),
      created_at=kwargs.get('created_at', str_to_tz_dt('2018-01-01 00:00')))
  post_sync.send(sender=Reservation, instance=payment.reservation)
  return refund


def get_test_credit_card_fee(**kwargs):
  payment = kwargs.get('payment', None)
  if not payment:
    payment = get_test_payment(**kwargs)
  cc_fee = CreditCardFee.objects.create(
      payment=payment,
      description=kwargs.get('description', 'Now you are get fee!'),
      amount=kwargs.get('amount', Money('10.0', 'USD')))
  post_sync.send(sender=Reservation, instance=payment.reservation)
  return cc_fee


def get_test_resolution_category(**kwargs):
  return ResolutionCategory.objects.create(
      name=kwargs.get('name', 'Unable to collect'))


def get_test_resolution(**kwargs):
  reservation = kwargs.get('reservation', None)
  if not reservation:
    reservation = get_test_reservation(**kwargs)
  resolution_category = kwargs.get('resolution_category', None)
  if not resolution_category:
    resolution_category = get_test_resolution_category(**kwargs)
  return Resolution.objects.create(
      reservation=reservation,
      resolution_category=resolution_category,
      notes=kwargs.get('notes', 'Just some notes here.'),
      ideal_payin=kwargs.get('ideal_payin', Money('0', 'USD')),
      actual_payin=kwargs.get('actual_payin', Money('0', 'USD')))


class PaymentTests(TestCase):
  def test_payment_amount(self):
    reservation = get_test_reservation()
    payment1 = get_test_payment(
        reservation=reservation, amount=Money('100', 'USD'))
    get_test_refund(payment=payment1, amount=Money('10', 'USD'))
    get_test_payment(reservation=reservation, amount=Money('3', 'USD'))
    self.assertTrue(payment1.has_refunds())
    self.assertEqual(Money('10', 'USD'), payment1.get_refund_amount())
    self.assertEqual(Money('90', 'USD'), payment1.get_actual_amount())
    self.assertEqual(Money('93', 'USD'), reservation.get_actual_payin())


class LikelyAndIdealTests(TestCase):
  def test_get_actual_payin(self):
    is_test = get_test_reservation(
        guesty_id='g',
        actual_payin=Money('43.21', 'USD'),
        ideal_payin=Money('10.98', 'USD'), is_test_rental=True)
    self.assertEqual(Money('0', 'USD'), is_test.get_actual_payin())
    has_calculated = get_test_reservation(
        guesty_id='f',
        check_in=str_to_tz_dt('2018-11-01 16:00'),
        check_out=str_to_tz_dt('2018-11-02 11:00'),
        actual_payin=Money('43.21', 'USD'),
        ideal_payin=Money('10.98', 'USD'), status=CANCELED,
        canceled_at=str_to_tz_dt('2018-10-16 12:00'),
        first_name='Pizza', last_name='Steve', full_name='Pizza Steve')
    self.assertEqual(
        Money('43.21', 'USD'),
        has_calculated.get_actual_payin())
    has_payments = get_test_reservation(
        guesty_id='e',
        check_in=str_to_tz_dt('2018-11-01 16:00'),
        check_out=str_to_tz_dt('2018-11-02 11:00'),
        canceled_at=str_to_tz_dt('2018-10-16 12:00'),
        status=CANCELED, ideal_payin=Money('11.11', 'USD'))
    get_test_payment(reservation=has_payments, amount=Money('54.32', 'USD'))
    self.assertEqual(
        Money('54.32', 'USD'), has_payments.get_actual_payin())
    canceled_1 = get_test_reservation(
        guesty_id='d',
        check_in=str_to_tz_dt('2018-11-01 16:00'),
        check_out=str_to_tz_dt('2018-11-02 11:00'),
        canceled_at=str_to_tz_dt('2018-10-16 12:00'),
        status=CANCELED, ideal_payin=Money('65.43', 'USD'))
    self.assertEqual(Money('0', 'USD'), canceled_1.get_actual_payin())
    canceled_2 = get_test_reservation(
        guesty_id='dd',
        check_in=str_to_tz_dt('2019-05-01 16:00'),  # Distant future!
        check_out=str_to_tz_dt('2019-05-02 11:00'),
        canceled_at=str_to_tz_dt('2018-10-16 12:00'),
        status=CANCELED, ideal_payin=Money('0', 'USD'),
        actual_payin=Money('100', 'USD'))
    self.assertEqual(Money('100', 'USD'), canceled_2.get_actual_payin())
    old_airbnb = get_test_reservation(
        guesty_id='c',
        channel=AIRBNB, check_in=str_to_tz_dt('2018-05-27 16:00'),
        check_out=str_to_tz_dt('2018-05-28 11:00'),
        status=CONFIRMED, ideal_payin=Money('76.54', 'USD'))
    self.assertEqual(Money('76.54', 'USD'), old_airbnb.get_actual_payin())
    imported_airbnb = get_test_reservation(
        guesty_id='bc',
        channel=AIRBNB, check_in=str_to_tz_dt('2019-01-01 16:00'),
        check_out=str_to_tz_dt('2019-01-02 16:00'),
        imported_at=str_to_tz_dt('2019-02-01'),
        status=CONFIRMED, ideal_payin=Money('77.55', 'USD'))
    self.assertEqual(Money('77.55', 'USD'), imported_airbnb.get_actual_payin())
    hasnt_happened_yet = get_test_reservation(
        guesty_id='b',
        check_in=str_to_tz_dt('2019-05-01 16:00'),
        check_out=str_to_tz_dt('2019-05-02 11:00'), status=CONFIRMED,
        ideal_payin=Money('76.54', 'USD'))
    self.assertEqual(
        Money('0', 'USD'),
        hasnt_happened_yet.get_actual_payin(
            nnow=str_to_tz_dt('2019-01-01 12:00')))
    only_apts = get_test_reservation(
        guesty_id='a',
        channel=ONLY_APARTMENTS, ideal_payin=Money('87.65', 'USD'),
        check_in=str_to_tz_dt('2019-01-01 16:00'),
        check_out=str_to_tz_dt('2019-01-02 11:00'), status=CONFIRMED)
    self.assertEqual(
        Money('87.65', 'USD'),
        only_apts.get_actual_payin(nnow=str_to_tz_dt('2019-05-01 12:00')))
    no_guesty_id = get_test_reservation(
        channel=AIRBNB, ideal_payin=Money('22.33', 'USD'),
        check_in=str_to_tz_dt('2019-01-01 16:00'),
        check_out=str_to_tz_dt('2019-01-02 11:00'), status=CONFIRMED,
        guesty_id=None)
    self.assertEqual(
        Money('22.33', 'USD'),
        no_guesty_id.get_actual_payin(nnow=str_to_tz_dt('2019-05-01 12:00')))

    problems = Reservation.objects.likely_payin_not_ideal_payin(
        nnow=str_to_tz_dt('2019-01-15 12:00'))
    expected = set([has_calculated, has_payments, canceled_1, canceled_2])
    self.assertEqual(expected, set(problems))


class ReservationTests(TestCase):
  def test_handle_resolve_payin_post(self):
    reservation = get_test_reservation(
        actual_payin=Money('12', 'USD'), ideal_payin=Money('24', 'USD'))
    get_test_resolution_category(name='Unable to collect')
    request_post = {
        'resolution_category': 'Unable to collect', 'notes': 'Stuff.'}
    self.assertTrue(handle_resolve_payin_post(request_post, reservation))
    self.assertEqual(Money('24', 'USD'), reservation.resolution.ideal_payin)
    self.assertEqual(Money('12', 'USD'), reservation.resolution.actual_payin)

  def test_likely_payin_not_ideal_payin_airbnb_vs_booking(self):
    old_airbnb = get_test_reservation(
        guesty_id='a',
        check_in=str_to_tz_dt('2018-11-10 16:00'),
        check_out=str_to_tz_dt('2018-11-11 11:00'),
        room_line_item=Money('11.11', 'USD'), channel=AIRBNB)
    get_test_reservation(  # No payment expected yet.
        guesty_id='b',
        check_in=str_to_tz_dt('2018-11-15 16:00'),
        check_out=str_to_tz_dt('2018-11-16 11:00'),
        room_line_item=Money('22.22', 'USD'), channel=AIRBNB)
    old_bookingcom = get_test_reservation(
        guesty_id='c',
        check_in=str_to_tz_dt('2018-11-15 16:00'),
        check_out=str_to_tz_dt('2018-11-16 11:00'),
        room_line_item=Money('33.33', 'USD'), channel=BOOKINGCOM)
    get_test_reservation(  # No payment expected yet.
        guesty_id='d',
        check_in=str_to_tz_dt('2018-11-22 16:00'),
        check_out=str_to_tz_dt('2018-11-23 11:00'),
        room_line_item=Money('44.44', 'USD'), channel=BOOKINGCOM)
    problems = Reservation.objects.likely_payin_not_ideal_payin(
        nnow=str_to_tz_dt('2018-11-15 12:00'))
    self.assertEqual(set([old_airbnb, old_bookingcom]), set(problems))

  def test_get_likely_payin(self):
    res = get_test_reservation(
        actual_payin=Money('12.34', 'USD'),
        ideal_payin=Money('87.65', 'USD'),
        check_in=str_to_tz_dt('2019-01-01 16:00'),
        check_out=str_to_tz_dt('2019-01-02 11:00'), status=CONFIRMED)
    self.assertEqual(
        Money('12.34', 'USD'),
        res.get_likely_payin(str_to_tz_dt('2019-02-01 12:00')))
    self.assertEqual(
        Money('87.65', 'USD'),
        res.get_likely_payin(str_to_tz_dt('2018-12-01 12:00')))

  def test_get_reservation_end(self):
    try:
      get_test_reservation(
          check_in=str_to_tz_dt('2018-10-13 16:00'),
          check_out=str_to_tz_dt('2018-10-15 11:00'), status=CANCELED,
          canceled_at=str_to_tz_dt('2018-10-13 15:00')).get_reservation_end()
      self.fail('A res that\'s canceled before checkin should have no end.')
    except Exception:
      pass
    self.assertEqual(str_to_tz_dt('2018-10-14 11:00'), get_test_reservation(
        check_in=str_to_tz_dt('2018-10-13 16:00'),
        check_out=str_to_tz_dt('2018-10-15 11:00'), status=CANCELED,
        canceled_at=str_to_tz_dt('2018-10-14 10:00')).get_reservation_end())
    self.assertEqual(str_to_tz_dt('2018-10-15 11:00'), get_test_reservation(
        check_in=str_to_tz_dt('2018-10-13 16:00'),
        check_out=str_to_tz_dt('2018-10-15 11:00'),
        status=CONFIRMED).get_reservation_end())
    self.assertEqual(str_to_tz_dt('2018-10-15 11:00'), get_test_reservation(
        check_in=str_to_tz_dt('2018-10-13 16:00'),
        check_out=str_to_tz_dt('2018-10-15 11:00'), status=CANCELED,
        canceled_at=str_to_tz_dt('2018-11-04 15:00')).get_reservation_end())
    self.assertEqual(str_to_tz_dt('2018-10-15 11:00'), get_test_reservation(
        check_in=str_to_tz_dt('2018-10-13 16:00'),
        check_out=str_to_tz_dt('2018-10-15 11:00'), status=CANCELED,
        canceled_at=str_to_tz_dt('2018-10-14 12:00')).get_reservation_end())

    check_out_set_in_future = get_test_reservation(
        check_in=str_to_tz_dt('2018-10-13 16:00'),
        check_out=str_to_tz_dt('2018-10-16 11:00'), status=CONFIRMED,
        check_out_set_at=str_to_tz_dt('2018-10-16 10:00'))
    self.assertEqual(
        str_to_tz_dt('2018-10-16 11:00'),
        check_out_set_in_future.get_reservation_end())
    check_out_set_in_past = get_test_reservation(
        check_in=str_to_tz_dt('2018-10-13 16:00'),
        check_out=str_to_tz_dt('2018-10-16 11:00'), status=CONFIRMED,
        check_out_set_at=str_to_tz_dt('2018-10-16 12:00'))
    self.assertEqual(
        str_to_tz_dt('2018-10-17 11:00'),
        check_out_set_in_past.get_reservation_end())

  def test_has_security_deposit(self):
    res = get_test_reservation(
        maximum_authorization_hold=Money(10, 'USD'))
    self.assertFalse(res.has_security_deposit())
    res = get_test_reservation(
        maximum_authorization_hold=Money(300, 'USD'))
    self.assertTrue(res.has_security_deposit())

  def test_no_cc_info(self):
    yes = get_test_reservation(
        channel=BOOKINGCOM, valid_payments_exist=True,
        check_in=now() + timedelta(days=1),
        check_out=now() + timedelta(days=2), id_verified=False,
        guesty_id='whatever')
    get_test_reservation(  # no
        channel=BOOKINGCOM, valid_payments_exist=True,
        check_in=now() + timedelta(days=1),
        check_out=now() + timedelta(days=2), id_verified=False,
        cc_last_4='1234', cc_brand='VISA', guesty_id='idk')
    yes2 = get_test_reservation(
        channel=ONLY_APARTMENTS, valid_payments_exist=False,
        maximum_authorization_hold=Money(1, 'USD'),
        check_in=now() + timedelta(days=1),
        check_out=now() + timedelta(days=2), id_verified=False,
        guesty_id='aslskjenel')
    get_test_reservation(  # no
        channel=ONLY_APARTMENTS, valid_payments_exist=False,
        maximum_authorization_hold=None,
        check_in=now() + timedelta(days=1),
        check_out=now() + timedelta(days=2), id_verified=False,
        guesty_id='ikenelskdn')
    get_test_reservation(  # no
        channel=ONLY_APARTMENTS, valid_payments_exist=False,
        maximum_authorization_hold=Money(1, 'USD'), cc_last_4='1234',
        cc_brand='VISA', check_in=now() + timedelta(days=1),
        check_out=now() + timedelta(days=2), id_verified=False,
        guesty_id='kddnslenendnd')
    self.assertEqual([yes, yes2], list(Reservation.objects.no_cc_info()))

  def test_cc_action_required(self):
    yes = get_test_reservation(
        channel=BOOKINGCOM, valid_payments_exist=False,
        maximum_authorization_hold=None,
        check_in=now() + timedelta(days=1),
        check_out=now() + timedelta(days=2), guesty_id='whatever')
    yes2 = get_test_reservation(
        channel=ONLY_APARTMENTS, valid_payments_exist=False,
        maximum_authorization_hold=None,
        check_in=now() + timedelta(days=1),
        check_out=now() + timedelta(days=2), guesty_id='ewnsldk')
    yes3 = get_test_reservation(
        first_payment_scheduled_on=now() - timedelta(hours=2),
        channel=BOOKINGCOM, valid_payments_exist=False,
        maximum_authorization_hold=None,
        check_in=now() + timedelta(days=1),
        check_out=now() + timedelta(days=2), guesty_id='8yhbsgw')
    no3 = get_test_reservation(  # Copy of yes3 except for first_payment...
        first_payment_scheduled_on=now(),
        channel=BOOKINGCOM, valid_payments_exist=False,
        maximum_authorization_hold=None,
        check_in=now() + timedelta(days=1),
        check_out=now() + timedelta(days=2), guesty_id='skdenw3elskj')
    no = get_test_reservation(
        channel=BOOKINGCOM, valid_payments_exist=True,
        maximum_authorization_hold=None,
        check_in=now() + timedelta(days=1),
        check_out=now() + timedelta(days=2), guesty_id='idk')
    no2 = get_test_reservation(
        channel=ONLY_APARTMENTS, valid_payments_exist=False,
        maximum_authorization_hold=Money(1, 'USD'),
        check_in=now() + timedelta(days=1),
        check_out=now() + timedelta(days=2), guesty_id='blahblah')
    self.assertTrue(yes.cc_action_required())
    self.assertTrue(yes2.cc_action_required())
    self.assertTrue(yes3.cc_action_required())
    self.assertFalse(no.cc_action_required())
    self.assertFalse(no2.cc_action_required())
    self.assertFalse(no3.cc_action_required())
    self.assertEqual([yes, yes2, yes3], list(
        Reservation.objects.cc_action_required()))

  def test_expecting_payments(self):
    yes = get_test_reservation(
        status=CONFIRMED, guesty_id='MakeItHappenCapn',
        room_line_item=Money('100', 'USD'),
        check_in=now() + timedelta(days=1),
        check_out=now() + timedelta(days=2),
        channel=BOOKINGCOM, last_synced_at=str_to_tz_dt('2019-01-01'))
    waiting_for_cancellation_fees = get_test_reservation(
        status=CANCELED, guesty_id='WhydYouLetMeDoThat?',
        room_line_item=Money('100', 'USD'),
        check_in=now() - timedelta(hours=47),
        check_out=now() + timedelta(days=2),
        canceled_at=str_to_tz_dt('2018-10-16 12:00'),
        last_synced_at=str_to_tz_dt('2019-01-01'))
    get_test_reservation(  # recently_synced
        status=CONFIRMED, guesty_id='ImSupposedToBeUnderSupervision',
        room_line_item=Money('100', 'USD'),
        check_in=now() + timedelta(days=1),
        check_out=now() + timedelta(days=2),
        channel=BOOKINGCOM, last_synced_at=now() - timedelta(minutes=30))
    get_test_reservation(  # canceled_a_while_ago
        status=CANCELED, guesty_id='WellYouKnowWhat?Capitalism.',
        canceled_at=str_to_tz_dt('2018-10-16 12:00'),
        room_line_item=Money('100', 'USD'),
        check_in=now() - timedelta(days=10),
        check_out=now() + timedelta(days=2),
        channel=BOOKINGCOM, last_synced_at=str_to_tz_dt('2019-01-01'))
    get_test_reservation(  # no_guesty_reservation
        status=CONFIRMED, guesty_id=None,
        room_line_item=Money('100', 'USD'),
        check_in=now() + timedelta(days=1),
        check_out=now() + timedelta(days=2),
        channel=BOOKINGCOM, last_synced_at=str_to_tz_dt('2019-01-01'))
    get_test_reservation(  # distant_past_checkin
        status=CONFIRMED, guesty_id='UphillHeadwind',
        room_line_item=Money('100', 'USD'),
        check_in=now() - timedelta(days=15),
        check_out=now() + timedelta(days=1),
        channel=BOOKINGCOM, last_synced_at=str_to_tz_dt('2019-01-01'))
    no_balance_due = get_test_reservation(
        status=CONFIRMED, guesty_id='SaveThePlanet.WhyNot.',
        room_line_item=Money('100', 'USD'),
        check_in=now() + timedelta(days=1),
        check_out=now() + timedelta(days=2),
        channel=BOOKINGCOM, last_synced_at=str_to_tz_dt('2019-01-01'))
    get_test_payment(reservation=no_balance_due, amount=Money('100', 'USD'))

    def key(reservation):
      return reservation.pk
    self.assertEqual(
        sorted([yes, waiting_for_cancellation_fees], key=key),
        sorted(list(Reservation.objects.expecting_payments()), key=key))

  def test_get_overlapping(self):
    rental = get_test_rental()
    r_overlap_with_me = get_test_reservation(
        check_in='2018-02-10 16:00',
        check_out='2018-02-15 11:00',
        rental=rental)

    get_test_reservation(  # r_all_before
        check_in='2018-02-01 16:00',
        check_out='2018-02-10 11:00',
        rental=rental)
    r_co_in = get_test_reservation(
        check_in='2018-02-01 16:00',
        check_out='2018-02-10 17:00',
        rental=rental)
    r_all_in = get_test_reservation(
        check_in='2018-02-11 16:00',
        check_out='2018-02-12 11:00',
        rental=rental)
    r_ci_in = get_test_reservation(
        check_in='2018-02-11 16:00',
        check_out='2018-02-16 11:00',
        rental=rental)
    get_test_reservation(  # r_all_after
        check_in='2018-02-16 16:00',
        check_out='2018-02-17 11:00',
        rental=rental)

    overlapping = r_overlap_with_me.get_overlapping()
    got_overlapping_ids = set([overlap.pk for overlap in overlapping])
    expect_overlapping_ids = set([r_co_in.pk, r_all_in.pk, r_ci_in.pk])
    self.assertEqual(got_overlapping_ids, expect_overlapping_ids)

  def test_get_guest_feedback_form_link(self):
    from front.models import Conversation
    r = get_test_reservation(
        full_name='Donovan Jones',
        phone='1236540987',
        nickname='243 Montgoober st, Texas',
        check_in='2018-05-01 16:00',
        check_out='2018-05-04 11:00',
        issues='Nothing isn\'t not broken?!',
        guesty_id='beepboopbap',
        city='Texas',
        guest_count=3)
    Conversation.objects.create(to_phone='1236540987', convo_id='convoopity')
    expected = (
        'https://stayd.typeform.com/to/AHNpQk'
        '?guestname=Donovan+Jones'
        '&phone=1236540987'
        '&address=243+Montgoober+st%2C+Texas'
        '&startdate=2018-05-01'
        '&issues=Nothing+isn%27t+not+broken%3F%21'
        '&guestlink='
        'https%3A%2F%2Fapp.guesty.com%2Freservations%2Fbeepboopbap%2Fguests'
        '&city=Texas'
        '&reslength=3'
        '&frontlink=https%3A%2F%2Fapp.frontapp.com%2Fopen%2Fconvoopity')
    self.assertEqual(expected, r.get_guest_feedback_form_link())


class GetReservationFromQueryTests(TestCase):
  def test_get_reservation_from_query(self):
    # These 3 are the same except that the first and last are canceled.
    get_test_reservation(
        channel=AIRBNB, phone='1(917)608-4623', full_name='Ed Viesturs',
        first_name='Ed', last_name='Viesturs',
        check_in=now() - timedelta(days=1),
        canceled_at=str_to_tz_dt('2018-10-16 12:00'),
        check_out=now() + timedelta(days=1), status=CANCELED)
    res = get_test_reservation(
        channel=AIRBNB, phone='1(917)608-4623', full_name='Ed Viesturs',
        first_name='Ed', last_name='Viesturs',
        check_in=now() - timedelta(days=1),
        check_out=now() + timedelta(days=1))
    get_test_reservation(
        channel=AIRBNB, phone='1(917)608-4623', full_name='Ed Viesturs',
        first_name='Ed', last_name='Viesturs',
        check_in=now() - timedelta(days=1),
        check_out=now() + timedelta(days=1), status=CANCELED,
        canceled_at=str_to_tz_dt('2018-10-16 12:00'))

    get_test_reservation(
        channel=BOOKINGCOM, phone='1(555)666-4444', full_name='Ed Bronp',
        first_name='Ed', last_name='Bronp',
        check_in=now() - timedelta(days=1),
        check_out=now() + timedelta(days=1))
    self.assertIsNone(get_reservation_from_query({}))
    self.assertEqual(res, get_reservation_from_query({'phone': '19176084623'}))
    self.assertEqual(res, get_reservation_from_query({'name': 'Ed Viesturs'}))
    self.assertIsNone(get_reservation_from_query({'guest_first': 'Ed'}))
    self.assertEqual(res, get_reservation_from_query({
        'guest_first': 'Ed',
        'channel': 'airBnb'}))
