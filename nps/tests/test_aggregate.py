from datetime import date

from guest_messages.tests import get_test_email
from guesty.custom_field_ids import (
    NPS_RATE_US_EMAIL, CHECKOUT_INSTRUCTIONS_EMAIL)
from nps.models.aggregate import (
    aggregate_ratings_table, aggregate_data, get_total_sent_nps_emails,
    get_total_opened_nps_emails)
from nps.tests.test_rating import get_test_rating
from stats.models.stale import Stale
from rentals.tests import get_test_building, get_test_rental
from util.table import Cell, Row
from util.tests import TestCase
from util.timezone import str_to_tz_dt


class NPSEmailCountTests(TestCase):
  def setUp(self):
    super().setUp()
    get_test_email(
        guesty_custom_field_id=CHECKOUT_INSTRUCTIONS_EMAIL,
        when_did=str_to_tz_dt('2018-12-25'), opened=str_to_tz_dt('2018-12-25'))
    get_test_email(guesty_custom_field_id=NPS_RATE_US_EMAIL, when_did=None)
    get_test_email(
        guesty_custom_field_id=NPS_RATE_US_EMAIL,
        when_did=str_to_tz_dt('2019-12-25'))
    get_test_email(
        guesty_custom_field_id=NPS_RATE_US_EMAIL,
        when_did=str_to_tz_dt('2019-02-25'), opened=str_to_tz_dt('2019-02-25'))

  def test_get_total_sent_nps_emails(self):
    self.assertEqual(2, get_total_sent_nps_emails())

  def test_get_total_opened_nps_emails(self):
    self.assertEqual(1, get_total_opened_nps_emails())


class AggregateRatingsTableTests(TestCase):
  def setUp(self):
    super().setUp()
    self.building = get_test_building(
        nickname='Daves Diner', city='L.A.', state='California')
    self.rental = get_test_rental(
        building=self.building, apartment='#26', nickname='Daves Diner #26')
    get_test_rating(
        check_in=str_to_tz_dt('2018-12-25 16:00'),
        check_out=str_to_tz_dt('2018-12-26 11:00'), rental=self.rental,
        score=10, full_name='Billy Barb', guesty_id='aa',
        created_at=str_to_tz_dt('2018-12-27 11:00'))
    get_test_rating(
        check_in=str_to_tz_dt('2018-09-20 16:00'),
        check_out=str_to_tz_dt('2018-09-21 11:00'), rental=self.rental,
        score=7, full_name='Charlie Horse', guesty_id='bb',
        created_at=str_to_tz_dt('2018-12-27 11:00'))
    Stale.objects.fix()

  def test_aggregate_data(self):
    # Tree structure
    total = aggregate_data(str_to_tz_dt('2019-01-01'))
    self.assertEqual(['California'], list(total.children.keys()))
    california = total.children['California']
    self.assertEqual([self.building.city.pk], list(california.children.keys()))
    la = california.children[self.building.city.pk]
    self.assertEqual([self.building.pk], list(la.children.keys()))
    bldg = la.children[self.building.pk]
    self.assertEqual([self.rental.pk], list(bldg.children.keys()))
    rntl = bldg.children[self.rental.pk]
    self.assertEqual([], list(rntl.children.keys()))

    # Meta
    self.assertEqual('Total', total.title)
    self.assertEqual('', total.query_string)
    self.assertEqual('California', california.title)
    self.assertEqual('state=California', california.query_string)
    self.assertEqual('L.A.', la.title)
    self.assertEqual('city={}'.format(self.building.city.pk), la.query_string)
    self.assertEqual('Daves Diner', bldg.title)
    self.assertEqual(
        'building={}'.format(self.building.pk), bldg.query_string)
    self.assertEqual('#26', rntl.title)
    self.assertEqual('rental={}'.format(self.rental.pk), rntl.query_string)

    # Stats per month
    expected_data_keys = set([
        date(2018, 12, 1), date(2018, 9, 1),
        'Since 10/01/18', 'Since 07/01/18', 'Since 04/01/18',
        'Since 01/01/18'])
    for agg in [total, california, la, bldg, rntl]:
      self.assertEqual(
          expected_data_keys, set(agg.stats_per_month.keys()))
      self.assertEqual(100, agg.stats_per_month[date(2018, 12, 1)].nps())
      self.assertEqual(0, agg.stats_per_month[date(2018, 9, 1)].nps())
      self.assertEqual(100, agg.stats_per_month['Since 10/01/18'].nps())
      self.assertEqual(50, agg.stats_per_month['Since 07/01/18'].nps())
      self.assertEqual(50, agg.stats_per_month['Since 04/01/18'].nps())
      self.assertEqual(50, agg.stats_per_month['Since 01/01/18'].nps())

  def test_aggregate_ratings_table(self):
    table = aggregate_ratings_table(nnow=str_to_tz_dt('2018-12-31'))
    # The first column is the building name or whatever. That column has no
    # label.
    expected_headers = [
        '', 'December 18', 'November 18', 'October 18', 'September 18',
        'August 18', 'July 18', 'June 18', 'May 18', 'April 18', 'March 18',
        'February 18', 'January 18', 'Since 10/01/18', 'Since 07/01/18',
        'Since 04/01/18', 'Since 01/01/18']
    self.assertEqual(expected_headers, table.headers)

    december_base = '/nps_details/12-01-2018/01-01-2019/'

    # First 2 columns are correct
    table.rows[0].cells[0].assertEqual(
        Cell('Total', is_header=True, classes=['indent_0']))
    table.rows[0].cells[1].assertEqual(Cell(100, url=december_base))
    table.rows[1].cells[0].assertEqual(
        Cell('California', is_header=True, classes=['indent_1']))
    table.rows[1].cells[1].assertEqual(
        Cell(100, url='{}?state=California'.format(december_base)))
    table.rows[2].cells[0].assertEqual(
        Cell('L.A.', is_header=True, classes=['indent_2']))
    table.rows[2].cells[1].assertEqual(Cell(
        100, url='{}?city={}'.format(december_base, self.building.city.pk)))
    building_cell = Cell('Daves Diner', is_header=True, classes=['indent_3'])
    table.rows[3].cells[0].assertEqual(building_cell)
    building_december_cell = Cell(
        100, url='{}?building={}'.format(december_base, self.building.pk))
    table.rows[3].cells[1].assertEqual(building_december_cell)
    table.rows[4].cells[0].assertEqual(
        Cell('#26', is_header=True, classes=['indent_4']))
    table.rows[4].cells[1].assertEqual(Cell(
        100, url='{}?rental={}'.format(december_base, self.rental.pk)))

    # One whole row is correct
    september_cell = Cell(
        0, url='/nps_details/09-01-2018/10-01-2018/?building={}'.format(
            self.building.pk))
    ago_3_cell = Cell(
        100, url='/nps_details/10-01-2018/01-01-2019/?building={}'.format(
            self.building.pk))
    ago_6_cell = Cell(
        50, url='/nps_details/07-01-2018/01-01-2019/?building={}'.format(
            self.building.pk))
    ago_9_cell = Cell(
        50, url='/nps_details/04-01-2018/01-01-2019/?building={}'.format(
            self.building.pk))
    ago_12_cell = Cell(
        50, url='/nps_details/01-01-2018/01-01-2019/?building={}'.format(
            self.building.pk))
    expected_row = Row([
        building_cell, building_december_cell, None, None, september_cell,
        None, None, None, None, None, None,
        None, None, ago_3_cell, ago_6_cell,
        ago_9_cell, ago_12_cell])
    table.rows[3].assertEqual(expected_row)
