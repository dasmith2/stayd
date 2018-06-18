from django.test import TestCase
from django.utils.dateparse import parse_datetime, parse_date
from djmoney.money import Money

from reports.rent_revenue.rent_revenue import (
    pro_rated_month_count, get_rent_revenues)
from reports.rent_revenue.util import (
    total_days_and_within_from_to, reservation_charges_and_fees)
from reservations.models import KNOWN_LINE_ITEM_NAMES, ReservationLineItem
from reservations.tests import get_test_reservation


class TestHelperFunctions(TestCase):
  def test_get_rent_revenues(self):
    names = KNOWN_LINE_ITEM_NAMES

    inactive = get_test_reservation(
        True,
        check_in=parse_datetime('2018-02-01 20:00:00+00:00'),
        check_out=parse_datetime('2018-03-01 15:00:00+00:00'),
        market_rent=Money(1500, 'USD'),
        nickname='Lebanon zero',
        city='Lebanon',
        is_active=False)
    ReservationLineItem.objects.create(
        name=names.RENT,
        value=Money(100.0, 'USD'),
        reservation=inactive)

    leb_res_1 = get_test_reservation(
        True,
        check_in=parse_datetime('2018-02-01 20:00:00+00:00'),
        check_out=parse_datetime('2018-03-01 15:00:00+00:00'),
        market_rent=Money(1500, 'USD'),
        nickname='Lebanon one',
        city='Lebanon')
    ReservationLineItem.objects.create(
        name=names.RENT,
        value=Money(100.0, 'USD'),
        reservation=leb_res_1)
    leb_res_2 = get_test_reservation(
        True,
        check_in=parse_datetime('2018-02-15 20:00:00+00:00'),
        check_out=parse_datetime('2018-02-20 15:00:00+00:00'),
        market_rent=Money(500, 'USD'),
        nickname='Lebanon two',
        city='Lebanon')
    ReservationLineItem.objects.create(
        name=names.RENT,
        value=Money(100.0, 'USD'),
        reservation=leb_res_2)
    san_fran = get_test_reservation(
        True,
        check_in=parse_datetime('2018-02-15 20:00:00+00:00'),
        check_out=parse_datetime('2018-02-20 15:00:00+00:00'),
        market_rent=Money(3000, 'USD'),
        nickname='San Fran One',
        city='San Francisco')
    ReservationLineItem.objects.create(
        name=names.RENT,
        value=Money(100.0, 'USD'),
        reservation=san_fran)

    rent_revenues = get_rent_revenues(
        parse_date('2018-02-15'), parse_date('2018-03-01'))

    self.assertEqual(6, len(rent_revenues))

    self.assertEqual('Total', rent_revenues[0].name)
    self.assertEqual(Money(2500, 'USD'), rent_revenues[0].rent)
    self.assertEqual(Money(250, 'USD'), rent_revenues[0].total_charges)
    self.assertEqual(3 * 14, rent_revenues[0].days)
    self.assertEqual(24, rent_revenues[0].occupied_days)

    self.assertTrue(rent_revenues[0].adr())
    self.assertTrue(rent_revenues[0].occupancy_rate())
    self.assertTrue(rent_revenues[0].rev_par())

    self.assertEqual('Lebanon', rent_revenues[1].name)
    self.assertEqual(Money(1000, 'USD'), rent_revenues[1].rent)
    self.assertEqual(Money(150, 'USD'), rent_revenues[1].total_charges)
    self.assertEqual(2 * 14, rent_revenues[1].days)
    self.assertEqual(19, rent_revenues[1].occupied_days)
    self.assertEqual('Lebanon one', rent_revenues[2].name)
    self.assertEqual(Money(750, 'USD'), rent_revenues[2].rent)
    self.assertEqual(Money(50, 'USD'), rent_revenues[2].total_charges)
    self.assertEqual(14, rent_revenues[2].days)
    self.assertEqual(14, rent_revenues[2].occupied_days)
    self.assertEqual('Lebanon two', rent_revenues[3].name)
    self.assertEqual(Money(250, 'USD'), rent_revenues[3].rent)
    self.assertEqual(Money(100, 'USD'), rent_revenues[3].total_charges)
    self.assertEqual(14, rent_revenues[3].days)
    self.assertEqual(5, rent_revenues[3].occupied_days)
    self.assertEqual('San Francisco', rent_revenues[4].name)
    self.assertEqual(Money(1500, 'USD'), rent_revenues[4].rent)
    self.assertEqual(Money(100, 'USD'), rent_revenues[4].total_charges)
    self.assertEqual(14, rent_revenues[4].days)
    self.assertEqual(5, rent_revenues[4].occupied_days)
    self.assertEqual('San Fran One', rent_revenues[5].name)
    self.assertEqual(Money(1500, 'USD'), rent_revenues[5].rent)
    self.assertEqual(Money(100, 'USD'), rent_revenues[5].total_charges)
    self.assertEqual(14, rent_revenues[5].days)
    self.assertEqual(5, rent_revenues[5].occupied_days)

  def test_total_days_and_within_from_to(self):
    reservation = get_test_reservation(
        True,
        check_in=parse_datetime('2018-05-15 20:00:00+00:00'),
        check_out=parse_datetime('2018-05-17 15:00:00+00:00'))
    self.assertEqual((2, 0), total_days_and_within_from_to(
        reservation, parse_date('2018-05-14'), parse_date('2018-05-15')))
    self.assertEqual((2, 1), total_days_and_within_from_to(
        reservation, parse_date('2018-05-15'), parse_date('2018-05-16')))
    self.assertEqual((2, 1), total_days_and_within_from_to(
        reservation, parse_date('2018-05-16'), parse_date('2018-05-17')))
    self.assertEqual((2, 0), total_days_and_within_from_to(
        reservation, parse_date('2018-05-17'), parse_date('2018-05-18')))
    self.assertEqual((2, 2), total_days_and_within_from_to(
        reservation, parse_date('2018-05-15'), parse_date('2018-05-17')))
    self.assertEqual((2, 2), total_days_and_within_from_to(
        reservation, parse_date('2018-05-14'), parse_date('2018-05-18')))

  def test_reservation_charges_and_fees(self):
    reservation = get_test_reservation(True)
    names = KNOWN_LINE_ITEM_NAMES
    ReservationLineItem.objects.create(
        name=names.RENT,
        value=Money(100.0, 'USD'),
        reservation=reservation)
    ReservationLineItem.objects.create(
        name=names.HOST_CHANNEL_FEE,
        value=Money(-10.0, 'USD'),
        reservation=reservation)
    ReservationLineItem.objects.create(
        name=names.CLEANING_FEE,
        value=Money(50.0, 'USD'),
        reservation=reservation)
    charges_and_fees = reservation_charges_and_fees(reservation)
    self.assertEqual(charges_and_fees.total_charges, Money(150, 'USD'))
    self.assertEqual(charges_and_fees.cleaning_fee, Money(50, 'USD'))
    self.assertEqual(charges_and_fees.channel_fee, Money(10, 'USD'))

  def test_pro_rated_month_count(self):
    self.assertEqual(1.0, pro_rated_month_count(
        parse_date('2018-01-01'), parse_date('2018-02-01')))
    self.assertEqual(1.0, pro_rated_month_count(
        parse_date('2018-02-01'), parse_date('2018-03-01')))
    self.assertEqual(1.0, pro_rated_month_count(
        parse_date('2018-03-01'), parse_date('2018-04-01')))

    self.assertEqual(2.0, pro_rated_month_count(
        parse_date('2018-02-01'), parse_date('2018-04-01')))

    self.assertEqual(0.5, pro_rated_month_count(
        parse_date('2018-04-01'), parse_date('2018-04-16')))
    self.assertEqual(0.5, pro_rated_month_count(
        parse_date('2018-04-16'), parse_date('2018-05-01')))
