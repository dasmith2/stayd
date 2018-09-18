from util.tests import TestCase
from django.utils.dateparse import parse_datetime, parse_date
from djmoney.money import Money

from rentals.models import RENT
from rentals.tests import get_test_owner, get_test_monthly_expense
from reports.rent_revenue.rent_revenue import get_rent_revenues
from reports.rent_revenue.util import reservation_res_stats
from reservations.models import KNOWN_LINE_ITEM_NAMES, ReservationLineItem
from reservations.tests import get_test_reservation


class TestHelperFunctions(TestCase):
  def test_get_rent_revenues(self):
    names = KNOWN_LINE_ITEM_NAMES

    owner = get_test_owner(True, username='TheQueenofSpain')

    inactive = get_test_reservation(
        True,
        owner=owner,
        check_in=parse_datetime('2018-02-01 20:00:00+00:00'),
        check_out=parse_datetime('2018-03-01 15:00:00+00:00'),
        nickname='Lebanon zero',
        city='Lebanon',
        is_active=False)  # Rental.is_active False shouldn't show.
    get_test_monthly_expense(
        True, rental=inactive.rental, monthly_amount=Money(1000000, 'USD'),
        kind=RENT)
    ReservationLineItem.objects.create(
        name=names.RENT,
        value=Money(100.0, 'USD'),
        reservation=inactive)

    wrong_owner = get_test_reservation(
        True,
        check_in=parse_datetime('2018-02-01 20:00:00+00:00'),
        check_out=parse_datetime('2018-03-01 15:00:00+00:00'),
        nickname='Lebanon one',
        city='Lebanon')
    get_test_monthly_expense(
        True, rental=wrong_owner.rental, monthly_amount=Money(365, 'USD'),
        kind=RENT)
    ReservationLineItem.objects.create(
        name=names.RENT,
        value=Money(100.0, 'USD'),
        reservation=wrong_owner)

    leb_res_1 = get_test_reservation(
        True,
        owner=owner,
        check_in=parse_datetime('2018-02-01 20:00:00+00:00'),
        check_out=parse_datetime('2018-03-01 15:00:00+00:00'),
        nickname='Lebanon one',
        city='Lebanon')
    get_test_monthly_expense(
        True, rental=leb_res_1.rental, monthly_amount=Money(365 * 2, 'USD'),
        kind=RENT)
    ReservationLineItem.objects.create(
        name=names.RENT,
        value=Money(100.0, 'USD'),
        reservation=leb_res_1)
    leb_res_2 = get_test_reservation(
        True,
        owner=owner,
        check_in=parse_datetime('2018-02-15 20:00:00+00:00'),
        check_out=parse_datetime('2018-02-20 15:00:00+00:00'),
        nickname='Lebanon two',
        city='Lebanon')
    get_test_monthly_expense(
        True, rental=leb_res_2.rental, monthly_amount=Money(365 * 3, 'USD'),
        kind=RENT)
    ReservationLineItem.objects.create(
        name=names.RENT,
        value=Money(100.0, 'USD'),
        reservation=leb_res_2)
    san_fran = get_test_reservation(
        True,
        owner=owner,
        check_in=parse_datetime('2018-02-15 20:00:00+00:00'),
        check_out=parse_datetime('2018-02-20 15:00:00+00:00'),
        nickname='San Fran One',
        city='San Francisco')
    get_test_monthly_expense(
        True, rental=san_fran.rental, monthly_amount=Money(365 * 4, 'USD'),
        kind=RENT)
    ReservationLineItem.objects.create(
        name=names.RENT,
        value=Money(100.0, 'USD'),
        reservation=san_fran)

    # 14 days.
    rent_revenues = get_rent_revenues(
        parse_date('2018-02-15'), parse_date('2018-03-01'), owner_id=owner.pk)

    # One total, one for Lebanon and one for San Fran, one for each rental
    # besides Lebanon zero, the inactive one.
    self.assertEqual(6, len(rent_revenues))

    self.assertEqual('Total', rent_revenues[0].name)
    # A monthly rent of 365 means a daily rent of 12. Inactive and wrong owner
    # rentals shouldn't get counted. So monthly rents of
    # 2 * 365 + 3 * 365 + 4 * 365 = 9 * 365 means daily rents of
    # 9 * 12, and this is for 14 days.
    self.assertEqual(Money(9 * 12 * 14, 'USD'), rent_revenues[0].rent)
    self.assertEqual(Money(250, 'USD'), rent_revenues[0].total_charges)
    self.assertEqual(3 * 14, rent_revenues[0].max_occupancy)
    self.assertEqual(24, rent_revenues[0].occupied_days)

    self.assertTrue(rent_revenues[0].adr())
    self.assertTrue(rent_revenues[0].occupancy_rate())
    self.assertTrue(rent_revenues[0].rev_par())

    self.assertEqual('Lebanon', rent_revenues[1].name)
    self.assertEqual(Money(5 * 12 * 14, 'USD'), rent_revenues[1].rent)
    self.assertEqual(Money(150, 'USD'), rent_revenues[1].total_charges)
    self.assertEqual(2 * 14, rent_revenues[1].max_occupancy)
    self.assertEqual(19, rent_revenues[1].occupied_days)
    self.assertEqual('Lebanon one', rent_revenues[2].name)
    self.assertEqual(Money(2 * 12 * 14, 'USD'), rent_revenues[2].rent)
    self.assertEqual(Money(50, 'USD'), rent_revenues[2].total_charges)
    self.assertEqual(14, rent_revenues[2].max_occupancy)
    self.assertEqual(14, rent_revenues[2].occupied_days)
    self.assertEqual('Lebanon two', rent_revenues[3].name)
    self.assertEqual(Money(3 * 12 * 14, 'USD'), rent_revenues[3].rent)
    self.assertEqual(Money(100, 'USD'), rent_revenues[3].total_charges)
    self.assertEqual(14, rent_revenues[3].max_occupancy)
    self.assertEqual(5, rent_revenues[3].occupied_days)
    self.assertEqual('San Francisco', rent_revenues[4].name)
    self.assertEqual(Money(4 * 12 * 14, 'USD'), rent_revenues[4].rent)
    self.assertEqual(Money(100, 'USD'), rent_revenues[4].total_charges)
    self.assertEqual(14, rent_revenues[4].max_occupancy)
    self.assertEqual(5, rent_revenues[4].occupied_days)
    self.assertEqual('San Fran One', rent_revenues[5].name)
    self.assertEqual(Money(4 * 12 * 14, 'USD'), rent_revenues[5].rent)
    self.assertEqual(Money(100, 'USD'), rent_revenues[5].total_charges)
    self.assertEqual(14, rent_revenues[5].max_occupancy)
    self.assertEqual(5, rent_revenues[5].occupied_days)

  def test_reservation_res_stats(self):
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
    charges_and_fees = reservation_res_stats(reservation)
    self.assertEqual(charges_and_fees.total_charges, Money(150, 'USD'))
    self.assertEqual(charges_and_fees.cleaning_fees, Money(50, 'USD'))
    self.assertEqual(charges_and_fees.channel_fees, Money(10, 'USD'))
