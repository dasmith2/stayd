from datetime import date

from djmoney.money import Money

from netsuite.models.bill_table import reservations_for_bill_table, bill_table
from netsuite.tests.test_category_by_channel import (
    get_test_category_by_channel)
from netsuite.tests.test_location import get_test_location
from rentals.tests import get_test_rental
from reservations.models.money import KNOWN_LINE_ITEM_NAMES
from reservations.tests import (
    get_test_reservation, get_test_reservation_line_item, get_test_refund)
from util.channels import AIRBNB
from util.tests import TestCase
from util.timezone import str_to_tz_dt


class BillTests(TestCase):
  def setUp(self):
    super().setUp()
    self.rental = get_test_rental(nickname='Daves donuts')
    self._get_res(str_to_tz_dt('2018-11-15'), 'red_orange', self.rental)
    self.reservation = self._get_res(
        str_to_tz_dt('2018-12-15'), 'one_two', self.rental)
    self._get_res(str_to_tz_dt('2019-01-15'), 'honda_civic', self.rental)

  def _get_res(self, booked_at, channel_id, rental):
    res = get_test_reservation(
        booked_at=booked_at, channel=AIRBNB, channel_id=channel_id,
        check_in=str_to_tz_dt('2019-05-01 16:00'),
        check_out=str_to_tz_dt('2019-05-05 11:00'), rental=rental)
    get_test_reservation_line_item(
        reservation=res, value=Money(200, 'USD'),
        name=KNOWN_LINE_ITEM_NAMES.ACCOMMODATION_FARE)
    get_test_reservation_line_item(
        reservation=res, value=Money(100, 'USD'),
        name=KNOWN_LINE_ITEM_NAMES.CLEANING_FEES)
    get_test_reservation_line_item(
        reservation=res, value=-Money(10, 'USD'),
        name=KNOWN_LINE_ITEM_NAMES.HOST_CHANNEL_FEE)
    get_test_refund(reservation=res, amount=Money(20, 'USD'))
    return res

  def test_reservations_for_bill_table(self):
    self.assertEqual(
        [self.reservation],
        list(reservations_for_bill_table(date(2018, 12, 1), date(2019, 1, 1))))

  def test_bill_table_stuff_exists(self):
    get_test_category_by_channel(
        channel=AIRBNB,
        sales_category_name='AirBnB Sales!', sales_category_id=4567,
        fee_category_name='AriBnB Feeees!', fee_category_id=9876)
    get_test_location(rental=self.rental, location_id=555)

    table = bill_table([self.reservation])
    self.assertEqual(4, len(table.rows))
    self.assertEqual([
        '12/15/2018', 'December', 'one_two', 'one_two', 'airbnb',
        'AirBnB Sales!', 4567, 'Daves donuts', 555, 200], table.rows[0].cells)
    self.assertEqual([
        '12/15/2018', 'December', 'one_two', 'one_two', 'airbnb',
        'Cleaning Fee Income', 841, 'Daves donuts', 555,
        100], table.rows[1].cells)
    self.assertEqual([
        '12/15/2018', 'December', 'one_two', 'one_two', 'airbnb',
        'AriBnB Feeees!', 9876, 'Daves donuts', 555,
        10], table.rows[2].cells)
    self.assertEqual([
        '12/15/2018', 'December', 'one_two', 'one_two', 'airbnb',
        'AirBnB Sales!', 4567, 'Daves donuts', 555,
        -20], table.rows[3].cells)

  def test_bill_table_stuff_does_not_exist(self):
    bill_table([self.reservation])
