from datetime import date
from decimal import Decimal

from util.tests import TestCase
from djmoney.money import Money

from rentals.tests import get_test_rental, get_test_building
from reports.rent_revenue.reservation_list import (
    get_all_res_deets, get_all_res_deets_for_csv)
from reservations.models import (
    KNOWN_LINE_ITEM_NAMES, ReservationLineItem, CANCELED)
from reservations.tests import get_test_reservation, get_test_payment
from util.timezone import str_to_tz_dt


class ReservationListTests(TestCase):
  def setUp(self):
    super().setUp()
    building = get_test_building()
    rental = get_test_rental(building=building)
    # Should show up in the report.
    reservation = get_test_reservation(
        check_in='2018-02-01 15:00',
        check_out='2018-03-01 11:00',
        rental=rental,
        ideal_payin=Money(120.0, 'USD'),
        full_name='King Edgar the Weird',
        guesty_id='whatever')
    # Should not show up in the report.
    get_test_reservation(check_in='2018-02-01', check_out='2018-03-01')
    # This should show up because canceled reservations still affect stats
    # through cancellation fees.
    cancellation_fees = get_test_reservation(
        check_in='2018-02-01 16:00', check_out='2018-03-01 11:00',
        rental=rental, status=CANCELED, guesty_id='who_cares',
        canceled_at=str_to_tz_dt('2018-10-16 12:00'),
        full_name='Queen Booboo the confused')
    get_test_payment(reservation=cancellation_fees, amount=Money('10', 'USD'))
    # Unless there are no cancelation fees.
    get_test_reservation(
        check_in='2018-02-01 16:00', check_out='2018-03-01',
        canceled_at=str_to_tz_dt('2018-10-16 12:00'),
        rental=rental, status=CANCELED)

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
    ReservationLineItem.objects.create(
        name=names.CITY_TAX,
        value=Money(10.0, 'USD'),
        reservation=reservation)

    self.reservation = reservation

  def test_get_atom_res_deets(self):
    building = self.reservation.rental.building
    atom_1 = get_test_rental(building=building, accommodates=3)
    atom_2 = get_test_rental(building=building, accommodates=4)
    self.reservation.rental.is_combo_of.set([atom_1, atom_2])

    all_res_deets = get_all_res_deets(
        date(2018, 2, 1), date(2018, 2, 15), rental_id=atom_1.pk)
    res_deets_list = all_res_deets.res_deets_list
    res_deets = res_deets_list[0]
    self.assertEqual(3 / 7, res_deets.fraction_of_a_combo)
    expected_revenue_details = [
        ('Rooms revenue', Decimal('100.00')),
        ('Cleaning income', Decimal('30.00')),
        ('Taxes', Decimal('10.00')),
        ('Total revenue', Decimal('140')),
        ('Pro rated revenue', Decimal('30'))]
    self.assertEqual(expected_revenue_details, res_deets.revenue_details)

  def test_get_all_res_deets(self):
    reservation = self.reservation

    all_res_deets = get_all_res_deets(
        date(2018, 2, 1), date(2018, 2, 15), rental_id=reservation.rental.pk)
    res_deets_list = all_res_deets.res_deets_list
    self.assertEqual(2, len(res_deets_list))
    # get_all_res_deets is based on reservations_in_range which is ordered by
    # check_in
    res_deets = res_deets_list[0]
    self.assertEqual(
        'https://app.guesty.com/reservations/whatever/guests',
        res_deets.admin_url)
    self.assertEqual('whatever', res_deets.guesty_id)

    self.assertEqual(res_deets.stayd_web_id, reservation.pk)
    self.assertEqual(res_deets.guest_name, reservation.guest.get_name())
    self.assertEqual(res_deets.check_in, reservation.check_in)
    self.assertEqual(res_deets.check_out, reservation.check_out)
    self.assertEqual(res_deets.nights, 28)
    self.assertEqual(res_deets.nights_in_range, 14)
    expected_revenue_details = [
        ('Rooms revenue', Decimal('100.00')),
        ('Cleaning income', Decimal('30.00')),
        ('Taxes', Decimal('10.00')),
        ('Total revenue', Decimal('140')),
        ('Pro rated revenue', Decimal('70'))]
    self.assertEqual(expected_revenue_details, res_deets.revenue_details)
    expected_expense_details = [
        ('Cleaning fees', Decimal('30.00')),
        ('Channel fees', Decimal('20.00')),
        ('Taxes', Decimal('10.00')),
        ('Total expenses', Decimal('60')),
        ('Pro rated expenses', Decimal('30'))]
    self.assertEqual(expected_expense_details, res_deets.expense_details)
    expected_revenue_headers = [
        'Cancellation fees', 'Cleaning income', 'Pro rated revenue',
        'Rooms revenue', 'Taxes', 'Total revenue']
    self.assertEqual(expected_revenue_headers, all_res_deets.revenue_headers)
    expected_expense_headers = [
        'Channel fees', 'Cleaning fees', 'Pro rated expenses', 'Taxes',
        'Total expenses']
    self.assertEqual(expected_expense_headers, all_res_deets.expense_headers)

  def test_get_all_res_deets_for_csv(self):
    reservation = self.reservation

    rows = get_all_res_deets_for_csv(
        date(2018, 2, 1), date(2018, 2, 15),
        building_id=reservation.rental.building.pk, include_guests=True)
    # One for the header, one for the confirmed res and one for the canceled.
    self.assertEqual(3, len(rows))
    # Bit tricky here, to flatten the list deterministically I alphabetize the
    # revenue detail headers and then the expense detail headers, so they do
    # appear in a somewhat wonky order and taxes appears twice since it's in
    # both categories.
    expected_headers = [
        'Guesty ID', 'StaydWeb ID', 'Guest', 'Check in', 'Check out', 'Nights',
        'Pro rated nights', 'Combo rental fraction', 'Cancellation fees',
        'Cleaning income', 'Pro rated revenue', 'Rooms revenue', 'Taxes',
        'Total revenue', 'Prepayment', 'Prepayment date', 'Channel fees',
        'Cleaning fees', 'Pro rated expenses', 'Taxes', 'Total expenses']
    self.assertEqual(expected_headers, rows[0])
    keys_url = (
        'https://keys.hihoward.com/reports/reservation/{}'.format(
            reservation.pk))
    expected_row_1 = [
        'https://app.guesty.com/reservations/whatever/guests',
        keys_url, 'King Edgar the Weird',
        str_to_tz_dt('2018-02-01 15:00'), str_to_tz_dt('2018-03-01 11:00'), 28,
        14.0, 1.0, '', Decimal('30.00'), Decimal('70.000'), Decimal('100.00'),
        Decimal('10.00'), Decimal('140.00'), '', '', Decimal('20.00'),
        Decimal('30.00'), Decimal('30.000'), Decimal('10.00'),
        Decimal('60.00')]
    self.assertEqual(expected_row_1, rows[1])
    # This depends on an id for the canceled reservation which I don't happen
    # to have a reference for. It's probably fine.
    keys_url = rows[2][1]
    expected_row_2 = [
        'https://app.guesty.com/reservations/who_cares/guests', keys_url,
        'Queen Booboo the confused',
        str_to_tz_dt('2018-02-01 16:00'), str_to_tz_dt('2018-03-01 11:00'), 0,
        0.0, 1.0, Decimal('10.00'), '', Decimal('5.000'), '', '',
        Decimal('10.00'), '', '', '', '', Decimal('0.0'), '', Decimal('0')]
    self.assertEqual(expected_row_2, rows[2])

    rows = get_all_res_deets_for_csv(
        date(2018, 2, 1), date(2018, 2, 15),
        building_id=reservation.rental.building.pk, include_guests=False)
    self.assertEqual(3, len(rows))
    self.assertEqual(expected_headers[3:], rows[0])
    self.assertEqual(expected_row_1[3:], rows[1])
    self.assertEqual(expected_row_2[3:], rows[2])
