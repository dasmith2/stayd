from decimal import Decimal

from util.tests import TestCase
from django.utils.dateparse import parse_datetime, parse_date
from djmoney.money import Money

from rentals.models import RENT
from rentals.tests import (
    get_test_owner, get_test_monthly_expense, get_test_building)
from reports.rent_revenue.rent_revenue import get_rent_revenues
from reservations.models import (
    KNOWN_LINE_ITEM_NAMES, ReservationLineItem, Reservation)
from reservations.tests import (
    get_test_reservation, get_test_credit_card_fee, get_test_payment)
from util.signals import post_sync


class TestHelperFunctions(TestCase):
  def test_get_rent_revenues(self):
    """ This test takes forever due to the caching stuff. """
    names = KNOWN_LINE_ITEM_NAMES

    owner = get_test_owner(username='TheQueenofSpain')

    inactive = get_test_reservation(
        owner=owner,
        check_in=parse_datetime('2018-02-01 20:00:00+00:00'),
        check_out=parse_datetime('2018-03-01 15:00:00+00:00'),
        nickname='Lebanon zero',
        city='Lebanon',
        is_active=False,  # Rental.is_active False shouldn't show.
        ideal_payin=Money(100.0, 'USD'),
        actual_payin=Money(100.0, 'USD'))
    get_test_monthly_expense(
        rental=inactive.rental, monthly_amount=Money(1000000, 'USD'),
        kind=RENT)
    ReservationLineItem.objects.create(
        name=names.RENT,
        value=Money(100.0, 'USD'),
        reservation=inactive)
    post_sync.send(sender=Reservation, instance=inactive)

    wrong_owner = get_test_reservation(
        check_in=parse_datetime('2018-02-01 20:00:00+00:00'),
        check_out=parse_datetime('2018-03-01 15:00:00+00:00'),
        nickname='Lebanon wrong owner', city='Lebanon',
        ideal_payin=Money(100.0, 'USD'),
        actual_payin=Money(100.0, 'USD'))
    get_test_monthly_expense(
        rental=wrong_owner.rental, monthly_amount=Money(310, 'USD'),
        kind=RENT)
    ReservationLineItem.objects.create(
        name=names.RENT,
        value=Money(100.0, 'USD'),
        reservation=wrong_owner)
    post_sync.send(sender=Reservation, instance=wrong_owner)

    lebanon_building = get_test_building(
        city='Lebanon', nickname='Lebanon Palace', owner=owner)
    leb_res_1 = get_test_reservation(
        owner=owner,
        check_in=parse_datetime('2018-02-01 20:00:00+00:00'),
        check_out=parse_datetime('2018-03-01 15:00:00+00:00'),
        nickname='Lebanon apt 1', building=lebanon_building,
        ideal_payin=Money(100.0, 'USD'))
    leb_res_1_payment = get_test_payment(
        reservation=leb_res_1, amount=Money('100', 'USD'))
    get_test_credit_card_fee(
        amount=Money('10.0', 'USD'), payment=leb_res_1_payment)
    get_test_monthly_expense(
        rental=leb_res_1.rental, monthly_amount=Money(310 * 2, 'USD'),
        kind=RENT)
    ReservationLineItem.objects.create(
        name=names.RENT,
        value=Money(100.0, 'USD'),
        reservation=leb_res_1)
    post_sync.send(sender=Reservation, instance=leb_res_1)
    leb_res_2 = get_test_reservation(
        check_in=parse_datetime('2018-02-15 20:00:00+00:00'),
        check_out=parse_datetime('2018-02-20 15:00:00+00:00'),
        nickname='Lebanon apt 2', building=lebanon_building,
        ideal_payin=Money(100.0, 'USD'),
        actual_payin=Money(100.0, 'USD'))
    get_test_monthly_expense(
        rental=leb_res_2.rental, monthly_amount=Money(310 * 3, 'USD'),
        kind=RENT)
    ReservationLineItem.objects.create(
        name=names.RENT,
        value=Money(100.0, 'USD'),
        reservation=leb_res_2)
    post_sync.send(sender=Reservation, instance=leb_res_2)

    san_fran_building = get_test_building(
        city='San Francisco', nickname='San Fran Shack', owner=owner)
    san_fran = get_test_reservation(
        check_in=parse_datetime('2018-02-15 20:00:00+00:00'),
        check_out=parse_datetime('2018-02-20 15:00:00+00:00'),
        nickname='San Fran apt 1',
        building=san_fran_building,
        ideal_payin=Money(100.0, 'USD'),
        actual_payin=Money(100.0, 'USD'))
    get_test_monthly_expense(
        rental=san_fran.rental, monthly_amount=Money(310 * 4, 'USD'),
        kind=RENT)
    ReservationLineItem.objects.create(
        name=names.RENT,
        value=Money(100.0, 'USD'),
        reservation=san_fran)
    post_sync.send(sender=Reservation, instance=san_fran)

    # Stats are coming from a cache now which has to be informed when things
    # change (hence all those post_sync calls), and told when to fix stale
    # stats.
    from stats.models.stale import Stale
    Stale.objects.fix()

    # 14 days.
    rent_revenues = get_rent_revenues(
        parse_date('2018-02-15'), parse_date('2018-03-01'), owner_id=owner.pk)

    # One total, two for Lebanon and its building, two for San Fran and its
    # building, and one for each rental besides Lebanon zero, the inactive one.
    expect_rent_revenue_count = 8
    if expect_rent_revenue_count != len(rent_revenues):
      for rr in rent_revenues:
        print('{}, {}, {}'.format(rr.name, rr.indent, rr.sort_key))
    self.assertEqual(expect_rent_revenue_count, len(rent_revenues))

    self.assertEqual('Total', rent_revenues[0].name)
    self.assertEqual(0, rent_revenues[0].indent)
    # monthly rents of 2 * 310 + 3 * 310 + 4 * 310 = 9 * 310, but this is for
    # just half the month.
    self.assertEqual(Decimal(9 * 310 / 2), round(rent_revenues[0].rent))
    self.assert_dec_equal(Decimal('250'), rent_revenues[0].revenue())
    self.assert_dec_equal(Decimal('5'), rent_revenues[0].credit_card_fees)
    self.assertEqual(3 * 14, rent_revenues[0].nights_available)
    self.assertEqual(24, rent_revenues[0].nights_occupied)

    self.assertTrue(rent_revenues[0].adr())
    self.assertTrue(rent_revenues[0].occupancy_rate())
    self.assertTrue(rent_revenues[0].rev_par())

    self.assertEqual('Lebanon', rent_revenues[1].name)
    self.assertEqual(1, rent_revenues[1].indent)
    self.assertEqual(Decimal(5 * 310 / 2), round(rent_revenues[1].rent))
    self.assert_dec_equal(Decimal('150'), rent_revenues[1].revenue())
    self.assertEqual(2 * 14, rent_revenues[1].nights_available)
    self.assertEqual(19, rent_revenues[1].nights_occupied)

    self.assertEqual('Lebanon Palace', rent_revenues[2].name)
    self.assertEqual(2, rent_revenues[2].indent)
    self.assertEqual(Decimal(5 * 310 / 2), round(rent_revenues[2].rent))
    self.assert_dec_equal(Decimal('150'), rent_revenues[2].revenue())
    self.assertEqual(2 * 14, rent_revenues[2].nights_available)
    self.assertEqual(19, rent_revenues[2].nights_occupied)

    self.assertEqual('Lebanon apt 1', rent_revenues[3].name)
    self.assertEqual(3, rent_revenues[3].indent)
    self.assertEqual(Decimal(2 * 310 / 2), round(rent_revenues[3].rent))
    self.assert_dec_equal(Decimal('50'), rent_revenues[3].revenue())
    self.assertEqual(14, rent_revenues[3].nights_available)
    self.assertEqual(14, rent_revenues[3].nights_occupied)

    self.assertEqual('Lebanon apt 2', rent_revenues[4].name)
    self.assertEqual(Decimal(3 * 310 / 2), round(rent_revenues[4].rent))
    self.assert_dec_equal(Decimal('100'), rent_revenues[4].revenue())
    self.assertEqual(14, rent_revenues[4].nights_available)
    self.assertEqual(5, rent_revenues[4].nights_occupied)

    self.assertEqual('San Francisco', rent_revenues[5].name)
    self.assertEqual(Decimal(4 * 310 / 2), round(rent_revenues[5].rent))
    self.assert_dec_equal(Decimal('100'), rent_revenues[5].revenue())
    self.assertEqual(14, rent_revenues[5].nights_available)
    self.assertEqual(5, rent_revenues[5].nights_occupied)

    self.assertEqual('San Fran Shack', rent_revenues[6].name)
    self.assertEqual(Decimal(4 * 310 / 2), round(rent_revenues[6].rent))
    self.assert_dec_equal(Decimal('100'), rent_revenues[6].revenue())
    self.assertEqual(14, rent_revenues[6].nights_available)
    self.assertEqual(5, rent_revenues[6].nights_occupied)

    self.assertEqual('San Fran apt 1', rent_revenues[7].name)
    self.assertEqual(Decimal(4 * 310 / 2), round(rent_revenues[7].rent))
    self.assert_dec_equal(Decimal('100'), rent_revenues[7].revenue())
    self.assertEqual(14, rent_revenues[7].nights_available)
    self.assertEqual(5, rent_revenues[7].nights_occupied)
