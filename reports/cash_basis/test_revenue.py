from datetime import date

from djmoney.money import Money

from rentals.tests import get_test_building
from reports.cash_basis.revenue import (
    get_revenue_details_table, get_refund_details_table)
from reservations.models.money import KNOWN_LINE_ITEM_NAMES
from reservations.tests import (
    get_test_payment, get_test_refund, get_test_reservation,
    get_test_credit_card_fee, get_test_reservation_line_item)
from stripe.tests import get_test_charge
from util.tests import TestCase
from util.table import Cell, Row
from util.timezone import str_to_tz_dt


class RevenueTests(TestCase):
  def setUp(self):
    super().setUp()
    self.building = get_test_building()
    self.reservation = get_test_reservation(
        guesty_id='whatever', check_in=str_to_tz_dt('2019-02-16 16:00'),
        check_out=str_to_tz_dt('2019-02-17 11:00'), building=self.building,
        channel_id='rank_the_vices', full_name='Marc Magnificent')
    # So we got paid half of the ideal total so far.
    self.payment = get_test_payment(
        reservation=self.reservation, amount=Money('23', 'USD'),
        paid_at=str_to_tz_dt('2018-12-15'))

  def test_we_got_paid_seen_in_stripe(self):
    """ This is how Booking.com reservations are set up. """
    get_test_charge(payment=self.payment)
    get_test_credit_card_fee(payment=self.payment, amount=Money('1', 'USD'))
    # Line items total to $46, so that's the ideal payin. $23 is half the
    # ideal, so a payment of $23 should reflect half the City "service fee".
    get_test_reservation_line_item(
        reservation=self.reservation, name=KNOWN_LINE_ITEM_NAMES.CITY_TAX,
        value=Money('10', 'USD'))
    get_test_reservation_line_item(
        reservation=self.reservation, name=KNOWN_LINE_ITEM_NAMES.RENT,
        value=Money('36', 'USD'))
    table = get_revenue_details_table(
        self.building, date(2018, 12, 1), date(2019, 1, 1))
    res_cell = Cell(
        'rank_the_vices',
        url='https://app.guesty.com/reservations/whatever/guests')
    table.rows[0].assertEqual(Row([
        res_cell, 'Marc Magnificent', Money('23', 'USD'), date(2018, 12, 15),
        'We did.', Money('1', 'USD'), Money('5', 'USD')]))

  def test_get_revenue_details_table(self):
    get_test_payment(  # Outside date range
        reservation=self.reservation, amount=Money('1000000', 'USD'),
        paid_at=str_to_tz_dt('2018-11-15'))

    table = get_revenue_details_table(
        self.building, date(2018, 12, 1), date(2019, 1, 1))
    res_cell = Cell(
        'rank_the_vices',
        url='https://app.guesty.com/reservations/whatever/guests')
    table.rows[0].assertEqual(Row([
        res_cell, 'Marc Magnificent', Money('23', 'USD'), date(2018, 12, 15),
        '???', '', '']))

    """
    ??? I think this is old stuff that maybe doesn't exist any more or maybe I
    ripped out too many views when I was throwing things on the scrap heap?
    only time will tell!
    self.login(group=ACCOUNTANT)
    url_kwargs = {
        'from_date_str': date_to_url_str(date(2018, 12, 1)),
        'to_date_str': date_to_url_str(date(2019, 1, 1)),
        'building_id': self.building.pk}
    self.assert_get_contains(
        reverse('revenue_details', kwargs=url_kwargs), 'Marc Magnificent')
    self.assert_get_contains(
        reverse('revenue_details_csv', kwargs=url_kwargs), 'Marc Magnificent')
    """

  def test_get_refund_details_table(self):
    get_test_refund(
        created_at=str_to_tz_dt('2019-01-15'), amount=Money('19', 'USD'),
        payment=self.payment)
    get_test_refund(  # Outside date range
        created_at=str_to_tz_dt('2019-03-15'), amount=Money('1', 'USD'),
        payment=self.payment)

    table = get_refund_details_table(
        self.building, date(2019, 1, 1), date(2019, 2, 1))
    res_cell = Cell(
        'rank_the_vices',
        url='https://app.guesty.com/reservations/whatever/guests')
    table.rows[0].assertEqual(Row([
        res_cell, 'Marc Magnificent', Money('19', 'USD'), date(2019, 1, 15)]))

    """
    ??? I think this is old stuff that maybe doesn't exist any more or maybe I
    ripped out too many views when I was throwing things on the scrap heap?
    only time will tell!
    self.login(group=ACCOUNTANT)
    url_kwargs = {
        'from_date_str': date_to_url_str(date(2019, 1, 1)),
        'to_date_str': date_to_url_str(date(2019, 2, 1)),
        'building_id': self.building.pk}
    self.assert_get_contains(
        reverse('refund_details', kwargs=url_kwargs), 'Marc Magnificent')
    self.assert_get_contains(
        reverse('refund_details_csv', kwargs=url_kwargs), 'Marc Magnificent')
    """
