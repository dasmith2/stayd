from datetime import datetime, timedelta
import random
import string

from django.utils.timezone import make_aware, now
from djmoney.money import Money
from util.tests import TestCase

from guests.tests import get_test_guest
from rentals.tests import get_test_rental
from reservations.models import Reservation, CONFIRMED
from util.channels import BOOKINGCOM, AIRBNB, ONLY_APARTMENTS
from util.timezone import parse_dt


def get_test_reservation(create, **kwargs):
  check_in = parse_dt(
      kwargs.get('check_in', make_aware(datetime(2018, 5, 26, 15))))
  check_out = parse_dt(
      kwargs.get('check_out', make_aware(datetime(2018, 5, 28, 11))))

  guest = get_test_guest(create, **kwargs)
  rental = get_test_rental(create, **kwargs)
  random_channel_id = ''.join(
      random.choice(string.ascii_uppercase + string.digits) for _ in range(7))
  reservation = Reservation(
      channel_reservation_id=kwargs.get(
          'channel_reservation_id', random_channel_id),
      guest=kwargs.get('guest', guest),
      anonymized_email=kwargs.get('anonymized_email', 'akendks087@airbnb.com'),
      check_in=check_in,
      check_out=check_out,
      booked_at=kwargs.get('booked_at', make_aware(datetime(2018, 5, 25, 15))),
      planned_arrival=kwargs.get('planned_arrival', None),
      id_verified=kwargs.get('id_verified', False),
      rental=kwargs.get('rental', rental),
      channel=kwargs.get('channel', AIRBNB),
      price_per_night=kwargs.get('price_per_night', Money(125, 'USD')),
      night_count=kwargs.get('night_count', 2),
      total_payin=kwargs.get('total_payin', Money(340, 'USD')),
      is_paid_in=kwargs.get('is_paid_in', True),
      balance_due=kwargs.get('balance_due', Money(0, 'USD')),
      valid_payments_exist=kwargs.get('valid_payments_exist', True),
      maximum_authorization_hold=kwargs.get(
          'maximum_authorization_hold', None),
      status=kwargs.get('status', CONFIRMED),
      cc_last_4=kwargs.get('cc_last_4', None),
      cc_brand=kwargs.get('cc_brand', None))
  if reservation.check_in > reservation.check_out:
    reservation.check_out = reservation.check_in + timedelta(days=2)
  if create:
    reservation.save()
    guesty_id = kwargs.get('guesty_id', '')
    if guesty_id:
      from guesty.models import GuestyReservation
      GuestyReservation.objects.create(
          reservation=reservation,
          guesty_id=guesty_id)
  return reservation


class ReservationTests(TestCase):
  def test_has_security_deposit(self):
    res = get_test_reservation(
        False, maximum_authorization_hold=Money(10, 'USD'))
    self.assertFalse(res.has_security_deposit())
    res = get_test_reservation(
        False, maximum_authorization_hold=Money(300, 'USD'))
    self.assertTrue(res.has_security_deposit())

  def test_no_cc_info(self):
    yes = get_test_reservation(
        True, channel=BOOKINGCOM, valid_payments_exist=True,
        check_in=now() + timedelta(days=1), id_verified=False,
        guesty_id='whatever')
    get_test_reservation(  # no
        True, channel=BOOKINGCOM, valid_payments_exist=True,
        check_in=now() + timedelta(days=1), id_verified=False,
        cc_last_4='1234', cc_brand='VISA', guesty_id='idk')
    yes2 = get_test_reservation(
        True, channel=ONLY_APARTMENTS, valid_payments_exist=False,
        maximum_authorization_hold=Money(1, 'USD'),
        check_in=now() + timedelta(days=1), id_verified=False,
        guesty_id='aslskjenel')
    get_test_reservation(  # no
        True, channel=ONLY_APARTMENTS, valid_payments_exist=False,
        maximum_authorization_hold=None,
        check_in=now() + timedelta(days=1), id_verified=False,
        guesty_id='ikenelskdn')
    get_test_reservation(  # no
        True, channel=ONLY_APARTMENTS, valid_payments_exist=False,
        maximum_authorization_hold=Money(1, 'USD'), cc_last_4='1234',
        cc_brand='VISA', check_in=now() + timedelta(days=1), id_verified=False,
        guesty_id='kddnslenendnd')
    self.assertEqual([yes, yes2], list(Reservation.objects.no_cc_info()))

  def test_cc_action_required(self):
    yes = get_test_reservation(
        True, channel=BOOKINGCOM, valid_payments_exist=False,
        maximum_authorization_hold=None,
        check_in=now() + timedelta(days=1), guesty_id='whatever')
    yes2 = get_test_reservation(
        True, channel=ONLY_APARTMENTS, valid_payments_exist=False,
        maximum_authorization_hold=None,
        check_in=now() + timedelta(days=1), guesty_id='ewnsldk')
    no = get_test_reservation(
        True, channel=BOOKINGCOM, valid_payments_exist=True,
        maximum_authorization_hold=None,
        check_in=now() + timedelta(days=1), guesty_id='idk')
    no2 = get_test_reservation(
        True, channel=ONLY_APARTMENTS, valid_payments_exist=False,
        maximum_authorization_hold=Money(1, 'USD'),
        check_in=now() + timedelta(days=1), guesty_id='blahblah')
    self.assertEqual([yes, yes2], list(
        Reservation.objects.cc_action_required()))
    self.assertTrue(yes.cc_action_required())
    self.assertTrue(yes2.cc_action_required())
    self.assertFalse(no.cc_action_required())
    self.assertFalse(no2.cc_action_required())

  def test_expecting_payments(self):
    yes = get_test_reservation(
        True, is_paid_in=False, check_in=now() + timedelta(days=1),
        guesty_id='whatever')
    get_test_reservation(  # no
        True, is_paid_in=True, check_in=now() + timedelta(days=1),
        guesty_id='idk')
    self.assertEqual([yes], list(Reservation.objects.expecting_payments()))

  def test_get_overlapping(self):
    rental = get_test_rental(True)
    r_overlap_with_me = get_test_reservation(
        True,
        check_in='2018-02-10 16:00',
        check_out='2018-02-15 11:00',
        rental=rental)

    get_test_reservation(  # r_all_before
        True,
        check_in='2018-02-01 16:00',
        check_out='2018-02-10 11:00',
        rental=rental)
    r_co_in = get_test_reservation(
        True,
        check_in='2018-02-01 16:00',
        check_out='2018-02-10 17:00',
        rental=rental)
    r_all_in = get_test_reservation(
        True,
        check_in='2018-02-11 16:00',
        check_out='2018-02-12 11:00',
        rental=rental)
    r_ci_in = get_test_reservation(
        True,
        check_in='2018-02-11 16:00',
        check_out='2018-02-16 11:00',
        rental=rental)
    get_test_reservation(  # r_all_after
        True,
        check_in='2018-02-16 16:00',
        check_out='2018-02-17 11:00',
        rental=rental)

    overlapping = r_overlap_with_me.get_overlapping()
    got_overlapping_ids = set([overlap.pk for overlap in overlapping])
    expect_overlapping_ids = set([r_co_in.pk, r_all_in.pk, r_ci_in.pk])
    self.assertEqual(got_overlapping_ids, expect_overlapping_ids)
