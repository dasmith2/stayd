from datetime import date

from django.shortcuts import reverse
from djmoney.money import Money

from rentals.tests import get_test_building
from reports.cash_basis.cash_basis import get_cash_basis_table
from reports.cash_basis.coconut import get_building_coconut_transactions_table
from reservations.tests.tests import (
    get_test_payment, get_test_refund, get_test_reservation)
from util.channels import BOOKINGCOM
from util.table import Row, Cell
from util.tests import TestCase
from util.timezone import str_to_tz_dt
from util.urls import date_to_url_str
from xxero.tests.test_coconuts import get_test_coconut
from xxero.tests.test_tracking import get_test_tracking_option
from xxero.tests.test_transactions import (
    get_test_line_item, get_test_transaction)


class CashBasisTests(TestCase):
  def setUp(self):
    super().setUp()
    """      Janes    Susans
    Payments $200.00  $0.00
    Refunds  $300.00  $0.00
    Apples   $15.00   $17.00
    Mangos   $20.00   $0.00
    """
    self.susans_building = get_test_building(nickname='Susans')
    susans_option = get_test_tracking_option(
        building=self.susans_building, name='Susans')
    self.janes_building = get_test_building(nickname='Janes')
    janes_option = get_test_tracking_option(
        building=self.janes_building, name='Janes')
    bobs_building = get_test_building(
        nickname='Bobs test building', is_active=False)
    bobs_option = get_test_tracking_option(
        building=bobs_building, name='Bobs')
    self.mangos_coconut = get_test_coconut(code='661', name='Mangos')
    self.apples_coconut = get_test_coconut(code='772', name='Apples')

    reservation = get_test_reservation(
        check_in=str_to_tz_dt('2018-05-15 16:00'),
        check_out=str_to_tz_dt('2018-05-16 11:00'),
        building=self.janes_building, channel=BOOKINGCOM)
    payment = get_test_payment(
        reservation=reservation, amount=Money('200', 'USD'),
        paid_at=str_to_tz_dt('2018-01-25'))
    get_test_refund(
        payment=payment, amount=Money('300', 'USD'),
        created_at=str_to_tz_dt('2018-01-26'))
    payment_outside = get_test_payment(  # Outside date range
        reservation=reservation, amount=Money('20000', 'USD'),
        paid_at=str_to_tz_dt('2018-02-25'))
    get_test_refund(  # Outside date range
        payment=payment_outside, amount=Money('30000', 'USD'),
        created_at=str_to_tz_dt('2018-02-26'))

    janes_transaction_1 = get_test_transaction(
        when=date(2018, 1, 1), amount=Money('9', 'USD'), name='Big box store',
        bank_transaction_id='33333333-3333-3333-3333-333333333333',
        account_id='11111111-1111-1111-1111-111111111111',
        reference='Big reference')
    get_test_line_item(
        transaction=janes_transaction_1, amount=Money('9', 'USD'),
        coconut=self.mangos_coconut, tracking_options=[janes_option])

    janes_transaction_2 = get_test_transaction(
        when=date(2018, 1, 5), amount=Money('26', 'USD'),
        bank_transaction_id='44444444-4444-4444-4444-444444444444',
        name='Small box store',
        account_id='22222222-2222-2222-2222-222222222222')
    get_test_line_item(
        transaction=janes_transaction_2, amount=Money('11', 'USD'),
        coconut=self.mangos_coconut, tracking_options=[janes_option])
    get_test_line_item(
        transaction=janes_transaction_2, amount=Money('15', 'USD'),
        coconut=self.apples_coconut, tracking_options=[janes_option])

    get_test_line_item(
        when=date(2018, 1, 15), amount=Money('17', 'USD'),
        coconut=self.apples_coconut, tracking_options=[susans_option])

    get_test_line_item(  # Outside date range
        when=date(2018, 2, 1), amount=Money('10000000', 'USD'),
        coconut=self.mangos_coconut, tracking_options=[janes_option])
    get_test_line_item(  # No coconut.
        when=date(2018, 1, 1), amount=Money('10000000', 'USD'), coconut=None,
        tracking_options=[janes_option])
    get_test_line_item(  # No tracking.
        when=date(2018, 1, 1), amount=Money('10000000', 'USD'),
        coconut=self.mangos_coconut, tracking_options=[])
    get_test_line_item(  # Irrelevant tracking.
        when=date(2018, 1, 1), amount=Money('10000000', 'USD'),
        coconut=self.mangos_coconut,
        tracking_options=[get_test_tracking_option()])
    get_test_line_item(  # Inactive building
        when=date(2018, 1, 15), amount=Money('17', 'USD'),
        coconut=self.apples_coconut, tracking_options=[bobs_option])

  def test_get_building_coconut_transactions_table(self):
    table = get_building_coconut_transactions_table(
        date(2018, 1, 1), date(2018, 2, 1), self.mangos_coconut.pk,
        self.janes_building.pk)

    fours_url = (
        'https://go.xero.com/Bank/ViewTransaction.aspx?'
        'bankTransactionID=44444444-4444-4444-4444-444444444444&'
        'accountId=22222222-2222-2222-2222-222222222222')
    fours_id = Cell('44444444-4444-4444-4444-444444444444', url=fours_url)
    table.rows[0].assertEqual(Row(cells=[
        fours_id, 'Small box store', '', date(2018, 1, 5),
        Money('26.00', 'USD'), '', '', '']))
    table.rows[1].assertEqual(Row(cells=[
        '', '', '', '', '', Money('11.00', 'USD'), '661', 'Mangos']))
    table.rows[2].assertEqual(Row(cells=[
        '', '', '', '', '', Money('15.00', 'USD'), '772', 'Apples']))

    threes_url = (
        'https://go.xero.com/Bank/ViewTransaction.aspx?'
        'bankTransactionID=33333333-3333-3333-3333-333333333333&'
        'accountId=11111111-1111-1111-1111-111111111111')
    threes_id = Cell('33333333-3333-3333-3333-333333333333', url=threes_url)
    table.rows[3].assertEqual(Row(cells=[
        threes_id, 'Big box store', 'Big reference', date(2018, 1, 1),
        Money('9.00', 'USD'), '', '', '']))
    table.rows[4].assertEqual(Row(cells=[
        '', '', '', '', '', Money('9.00', 'USD'), '661', 'Mangos']))

    self.login(is_superuser=True)
    url = reverse('coconut_details', kwargs={
        'from_date_str': date_to_url_str(date(2018, 1, 1)),
        'to_date_str': date_to_url_str(date(2018, 2, 1)),
        'coconut_id': self.mangos_coconut.pk,
        'building_id': self.janes_building.pk})
    self.assert_get_contains(url, threes_url)

    url = reverse('coconut_details_csv', kwargs={
        'from_date_str': date_to_url_str(date(2018, 1, 1)),
        'to_date_str': date_to_url_str(date(2018, 2, 1)),
        'coconut_id': self.mangos_coconut.pk,
        'building_id': self.janes_building.pk})
    self.assert_get_contains(url, '33333333-3333-3333-3333-333333333333')

  def test_get_cash_basis_table(self):
    table = get_cash_basis_table(date(2018, 1, 1), date(2018, 2, 1))
    self.assertEqual(['', 'Janes', 'Susans'], table.headers)

    self.assertEqual(4, len(table.rows))

    payment_url = '/reports/revenue_details/01-01-2018/02-01-2018/{}/'
    table.rows[0].assertEqual(Row(cells=[
        Cell('Payments', is_header=True),
        Cell('$200.00', url=payment_url.format(self.janes_building.pk)),
        '']))

    refund_url = '/reports/refund_details/01-01-2018/02-01-2018/{}/'
    table.rows[1].assertEqual(Row(cells=[
        Cell('Refunds', is_header=True),
        Cell('$300.00', url=refund_url.format(self.janes_building.pk)),
        '']))

    building_coconut_format = (
        '/reports/coconut_details/01-01-2018/02-01-2018/{}/{}/')
    janes_apples_url = building_coconut_format.format(
        self.apples_coconut.pk, self.janes_building.pk)
    susans_apples_url = building_coconut_format.format(
        self.apples_coconut.pk, self.susans_building.pk)
    table.rows[2].assertEqual(Row(cells=[
        Cell('Apples', is_header=True), Cell('$15.00', url=janes_apples_url),
        Cell('$17.00', url=susans_apples_url)]))

    janes_mangos_url = building_coconut_format.format(
        self.mangos_coconut.pk, self.janes_building.pk)
    table.rows[3].assertEqual(Row(cells=[
        Cell('Mangos', is_header=True),
        Cell('$20.00', url=janes_mangos_url),
        '']))

    self.login(is_superuser=True)
    url = reverse('cash_basis', kwargs={
        'from_date_str': date_to_url_str(date(2018, 1, 1)),
        'to_date_str': date_to_url_str(date(2018, 2, 1))})
    content = self.get(url)
    self.assertTrue(content.find('Susans') >= 0)
    self.assertTrue(content.find('Mangos') >= 0)
