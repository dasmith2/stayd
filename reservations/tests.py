from datetime import datetime
import random
import string

from django.utils.timezone import make_aware
from django.test import TestCase

from guests.tests import get_test_guest
from listings.tests import get_test_listing
from rentals.tests import get_test_rental
from reservations.models import Reservation
from util.timezone import parse_dt


def get_test_reservation(create, **kwargs):
  check_in = parse_dt(
      kwargs.get('check_in', make_aware(datetime(2018, 5, 26, 15))))
  check_out = parse_dt(
      kwargs.get('check_out', make_aware(datetime(2018, 5, 28, 11))))

  guest = get_test_guest(create, **kwargs)
  listing = get_test_listing(create, **kwargs)
  random_channel_id = ''.join(
      random.choice(string.ascii_uppercase + string.digits) for _ in range(7))
  reservation = Reservation(
      channel_reservation_id=kwargs.get(
          'channel_reservation_id', random_channel_id),
      guest=kwargs.get('guest', guest),
      check_in=check_in,
      check_out=check_out,
      booked_at=kwargs.get('booked_at', make_aware(datetime(2018, 5, 25, 15))),
      planned_arrival=kwargs.get('planned_arrival', None),
      id_verified=kwargs.get('id_verified', False),
      listing=kwargs.get('listing', listing),
      price_per_night=kwargs.get('price_per_night', 125),
      night_count=kwargs.get('night_count', 2),
      total_payin=kwargs.get('total_payin', 340),
      is_paid_in=kwargs.get('is_paid_in', True),
      security_deposit=kwargs.get('security_deposit', None),
      status=kwargs.get('status', 'confirmed'),
      cc_last_4=kwargs.get('cc_last_4', None),
      cc_brand=kwargs.get('cc_brand', None))
  if create:
    reservation.save()
  return reservation


class ReservationTests(TestCase):
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
