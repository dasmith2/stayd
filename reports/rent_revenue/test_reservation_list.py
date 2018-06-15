from datetime import date

from django.test import TestCase
from djmoney.money import Money

from reports.rent_revenue.reservation_list import ReservationList
from reservations.models import KNOWN_LINE_ITEM_NAMES, ReservationLineItem
from reservations.tests import get_test_reservation


class ReservationListTests(TestCase):
  def test_single_reservation(self):
    reservation = get_test_reservation(
        True,
        check_in='2018-02-01',
        check_out='2018-03-01')
    names = KNOWN_LINE_ITEM_NAMES
    ReservationLineItem.objects.create(
        name=names.RENT,
        value=Money(100.0, 'USD'),
        reservation=reservation)
    ReservationLineItem.objects.create(
        name=names.HOST_CHANNEL_FEE,
        value=Money(-20.0, 'USD'),
        reservation=reservation)
    ReservationLineItem.objects.create(
        name=names.CLEANING_FEES,
        value=Money(30.0, 'USD'),
        reservation=reservation)

    res_list = ReservationList(
        reservation.listing.rental.pk, date(2018, 2, 1), date(2018, 2, 15))
    res_deets_list = res_list.get_res_deets_list()
    self.assertEqual(1, len(res_deets_list))
    res_deets = res_deets_list[0]
    self.assertIsNone(res_deets.guesty_url)
    self.assertIsNone(res_deets.guesty_id)

    self.assertEqual(res_deets.stayd_web_id, reservation.pk)
    self.assertEqual(res_deets.guest_name, reservation.guest.get_name())
    self.assertEqual(res_deets.check_in, reservation.check_in)
    self.assertEqual(res_deets.check_out, reservation.check_out)
    self.assertEqual(res_deets.nights, 28)
    self.assertEqual(res_deets.nights_in_range, 14)
    self.assertEqual(res_deets.percent_in_range, 50)
    self.assertEqual(res_deets.total_charges, Money(130.0, 'USD'))
    self.assertEqual(res_deets.total_charges_in_range, Money(65.0, 'USD'))
    self.assertEqual(res_deets.cleaning_fee, Money(30.0, 'USD'))
    self.assertEqual(res_deets.cleaning_fee_in_range, Money(15.0, 'USD'))
    self.assertEqual(res_deets.channel_fee, Money(20.0, 'USD'))
    self.assertEqual(res_deets.channel_fee_in_range, Money(10.0, 'USD'))
