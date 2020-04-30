from datetime import date

from django.contrib.auth.models import User
from djmoney.money import Money

from rentals.forms import RentalForm
from rentals.models import (
    City, Building, Rental, MonthlyExpense, RENT, SMSChannel)
from rentals.models.merge_rentals import (
    clean_up_dupe_rentals_table, merge_rentals)
from util.random_string import random_string
from util.table import Cell
from util.tests import TestCase
from util.timezone import str_to_tz_dt


def get_test_sms_channel(**kwargs):
  return SMSChannel.objects.create(
      name=kwargs.get('name', 'bloorgh'),
      identifier=kwargs.get('identifier', '123nlk'))


def get_test_monthly_expense(**kwargs):
  rental = kwargs.get('rental', None)
  if not rental:
    rental = get_test_rental(**kwargs)
  return MonthlyExpense.objects.create(
      rental=rental,
      start_date=kwargs.get('start_date', date(2017, 1, 1)),
      monthly_amount=kwargs.get('monthly_amount', Money(365 * 5, 'USD')),
      kind=kwargs.get('kind', RENT))


def get_test_owner(**kwargs):
  username = kwargs.get('username', random_string(10))
  existing = User.objects.filter(username=username).first()
  if existing:
    return existing
  return User.objects.create(
      username=username,
      first_name=kwargs.get('first_name', 'The queen'),
      last_name=kwargs.get('last_name', 'of England'),
      email=kwargs.get('email', 'thequeenofengland@gmail.com'),
      is_superuser=kwargs.get('is_superuser', False))


def get_test_city(**kwargs):
  name = kwargs.get('name', kwargs.get('city', None))
  if not name:
    name = 'Fargo'
  country = kwargs.get('country', 'United States')
  state = kwargs.get('state', 'ND')
  country = kwargs.get('country', 'United States')
  city = City.objects.filter(name=name, state=state).first()
  if city:
    if city.country != country:
      city.country = country
      city.save()
    return city
  return City.objects.create(name=name, state=state, country=country)


def get_test_building(**kwargs):
  owner = kwargs.get('owner', None)
  if not owner:
    owner = get_test_owner(**kwargs)
  default_nickname = '254 Penwipper, Fargo'
  while Building.objects.filter(nickname=default_nickname).exists():
    default_nickname += '1'
  city = kwargs.get('city', None)
  if isinstance(city, str):
    city = get_test_city(**kwargs)
  elif city is None:
    city = get_test_city(**kwargs)
  return Building.objects.create(
      city=city,
      street=kwargs.get('street', '254 Penwipper Dr.'),
      zipcode=kwargs.get('zipcode', '65432'),
      time_zone=kwargs.get('time_zone', 'US/Eastern'),
      owner=owner,
      nickname=kwargs.get('nickname', default_nickname),
      is_active=kwargs.get('is_active', True),
      alerts_email=kwargs.get('alerts_email', 'jerseycitystaff@stayd.com'),
      sms_staff_from=kwargs.get('sms_staff_from', None),
      background_check_guests=kwargs.get('background_check_guests', False))


def get_test_rental(**kwargs):
  building = kwargs.get('building', None)
  if not building:
    building = get_test_building(**kwargs)
  default_nickname = '254 Penwipper, Bismund'
  while Rental.objects.filter(nickname=default_nickname).exists():
    default_nickname += '1'
  rental = Rental(
      building=building,
      full_address=kwargs.get(
          'full_address', '254 Penwipper Dr., Bismund, Montana'),
      street=kwargs.get('street', ''),
      apartment=kwargs.get('apartment', None),
      accommodates=kwargs.get('accommodates', 2),
      bathrooms=kwargs.get('bathrooms', 1),
      bedrooms=kwargs.get('bedrooms', 1),
      property_type=kwargs.get('property_type', 'Apartment'),
      room_type=kwargs.get('room_type', 'Entire home/apt'),
      nickname=kwargs.get('nickname', default_nickname),
      is_active=kwargs.get('is_active', True),
      reports_start_date=kwargs.get('reports_start_date', date(2018, 1, 1)),
      reports_end_date=kwargs.get('reports_end_date', None),
      maintenance_purposes_only=kwargs.get('maintenance_purposes_only', False),
      main_checkin_instructions_link=kwargs.get(
          'main_checkin_instructions_link', ''),
      main_property_access_codes_in_order_of_use=kwargs.get(
          'main_property_access_codes_in_order_of_use', ''),
      master_access_code_building_door_electronic_lock=kwargs.get(
          'master_access_code_building_door_electronic_lock', ''),
      master_access_code_apartment_door_electronic_lock=kwargs.get(
          'master_access_code_apartment_door_electronic_lock', ''),
      backup_check_in_codes=kwargs.get(
          'backup_check_in_codes', ''),
      backup_check_in_instructions_link=kwargs.get(
          'backup_check_in_instructions_link', ''),
      wifi_network_name=kwargs.get(
          'wifi_network_name', ''),
      wifi_password=kwargs.get(
          'wifi_password', ''),
      building_trash_instructions=kwargs.get(
          'building_trash_instructions', ''),
      link_to_property_page_in_helpdocs=kwargs.get(
          'link_to_property_page_in_helpdocs', ''),
      google_maps_link=kwargs.get(
          'google_maps_link', ''),
      departure_check_list=kwargs.get(
          'departure_check_list', ''),
      local_bag_storage_info=kwargs.get(
          'local_bag_storage_info', ''),
      local_bag_storage_link=kwargs.get(
          'local_bag_storage_link', ''),
      parking_link=kwargs.get(
          'parking_link', ''),
      public_transportation_link=kwargs.get(
          'public_transportation_link', ''),
      local_recommendations_link=kwargs.get(
          'local_recommendations_link', ''),
      walking_to_nearest_path_stations=kwargs.get(
          'walking_to_nearest_path_stations', ''),
      parking_suggestions_no_links=kwargs.get(
          'parking_suggestions_no_links', ''),
      public_transport_no_link=kwargs.get(
          'public_transport_no_link', ''),
      walk_time_to_nearest_train=kwargs.get(
          'walk_time_to_nearest_train', ''),
      laundry_info=kwargs.get(
          'laundry_info', ''),
      online_store_available=kwargs.get(
          'online_store_available', False),
      is_test_rental=kwargs.get(
          'is_test_rental', False),
      extra_details=kwargs.get(
          'extra_details', ''),
      leave_the_keys=kwargs.get(
          'leave_the_keys', ''))
  rental.save()
  guesty_id = kwargs.get('guesty_id', '')
  if guesty_id:
    from guesty.models import GuestyRental
    GuestyRental.objects.create(
        rental=rental,
        guesty_id=guesty_id)
  rental.is_combo_of.set(kwargs.get('is_combo_of', []))
  return rental


class CleanUpDupeRentalsTests(TestCase):
  def setUp(self):
    super().setUp()
    self.keep_rental = get_test_rental(
        guesty_id='its_hard_to_argue', nickname='Argument house',
        apartment='12', full_address='12 Argument house, Insantiyville, IL')
    self.discard_rental = get_test_rental(guesty_id='with_insanity')
    self.monthly_expense = get_test_monthly_expense(rental=self.discard_rental)
    from reservations.tests import get_test_reservation
    self.reservation = get_test_reservation(rental=self.discard_rental)
    from stats.models.stats import Stats
    self.stats = Stats(
        from_date=date(2018, 12, 25), rental=self.discard_rental)
    from work.tests.test_rental import get_test_properly_rental
    from work.tests.test_work_co import get_test_work_co
    self.work_co = get_test_work_co()
    self.discard_properly_rental = get_test_properly_rental(
        rental=self.discard_rental, properly_property_id='blargh',
        source_property_id='blargh', clean_co=self.work_co,
        cleaning_flat_rate=Money('99', 'USD'))
    from work.tests.test_cleaning import get_test_cleaning_config
    self.cleaning_checklist = get_test_cleaning_config(
        properly_rental=self.discard_properly_rental)
    from work.tests.test_maintenance_checklist import (
        get_test_maintenance_checklist)
    self.checklist = get_test_maintenance_checklist(
        properly_rental=self.discard_properly_rental)
    from work.tests.test_repeat_work import get_test_repeat_config
    self.repeat_config = get_test_repeat_config(
        properly_rental=self.discard_properly_rental)
    from work.tests.test_one_off import get_test_one_off
    self.one_off = get_test_one_off(
        properly_rental=self.discard_properly_rental,
        offered_start_time=str_to_tz_dt('2018-12-25'))

    self.keep_properly_rental = get_test_properly_rental(
        rental=self.keep_rental, properly_property_id=None,
        source_property_id=None)
    from work.tests.test_cleaning import get_test_cleaning
    self.cleaning = get_test_cleaning(rental=self.discard_rental)
    from work.tests.test_maintenance import get_test_maintenance
    self.maintenance = get_test_maintenance(
        rental=self.discard_rental,
        offered_start_time=str_to_tz_dt('2018-12-25'))

  def test_clean_up_dupe_rentals(self):
    from stats.models.stats import Stats
    from work.models.rental import ProperlyRental
    merge_rentals(self.keep_rental, self.discard_rental)

    self.assertFalse(Rental.objects.filter(pk=self.discard_rental.pk).exists())
    self.monthly_expense.refresh_from_db()
    self.assertEqual(self.keep_rental, self.monthly_expense.rental)
    self.reservation.refresh_from_db()
    self.assertEqual(self.keep_rental, self.reservation.rental)
    self.assertFalse(Stats.objects.filter(pk=self.stats.pk).exists())
    self.assertFalse(ProperlyRental.objects.filter(
        pk=self.discard_properly_rental.pk).exists())
    self.cleaning.refresh_from_db()
    self.assertEqual(self.keep_rental, self.cleaning.rental)
    self.maintenance.refresh_from_db()
    self.assertEqual(self.keep_rental, self.maintenance.rental)
    self.cleaning_checklist.refresh_from_db()
    self.assertEqual(
        self.keep_properly_rental, self.cleaning_checklist.properly_rental)
    self.checklist.refresh_from_db()
    self.assertEqual(
        self.keep_properly_rental, self.checklist.properly_rental)
    self.repeat_config.refresh_from_db()
    self.assertEqual(
        self.keep_properly_rental, self.repeat_config.properly_rental)
    self.one_off.refresh_from_db()
    self.assertEqual(
        self.keep_properly_rental, self.one_off.properly_rental)
    self.keep_properly_rental.refresh_from_db()
    self.assertEqual(
        'blargh', self.keep_properly_rental.properly_property_id)
    self.assertEqual(
        'blargh', self.keep_properly_rental.source_property_id)
    self.assertEqual(
        self.work_co, self.keep_properly_rental.clean_co)
    self.assertEqual(
        Money('99', 'USD'), self.keep_properly_rental.cleaning_flat_rate)

  def test_clean_up_dupe_rentals_table(self):
    rentals = [self.keep_rental, self.discard_rental]
    table = clean_up_dupe_rentals_table(rentals, show_keep_this_one=True)
    expected_headers = [
        'Keep this one', 'Nickname', 'Apartment', 'Full address', 'Keys ID',
        'Guesty ID', 'Is active']
    self.assertEqual(expected_headers, table.headers)
    action_cell = Cell(
        additional_attrs={'data-rental-id': self.keep_rental.pk},
        classes=['keep_rental_cell'])
    expected_row_0 = [
        action_cell, 'Argument house', '12',
        '12 Argument house, Insantiyville, IL', self.keep_rental.pk,
        'its_hard_to_argue', True]
    self.assertEqual(expected_row_0, table.rows[0].cells)


class RentalFormTests(TestCase):
  def test_is_combo_rental(self):
    building = get_test_building()
    child = get_test_rental(
        building=building, nickname='Why dont you go play', apartment='golf')
    parent = get_test_rental(
        is_combo_of=[child], building=building,
        nickname='And count your money')
    self.assertFalse(child.is_combo_rental())
    self.assertTrue(parent.is_combo_rental())
    self.assertEqual('golf', parent.combo_unit_description)
    self.assertEqual([child], child.get_rentals())
    self.assertEqual([child], list(parent.get_rentals()))

  def test_cant_make_grandparent_combo_rentals(self):
    building = get_test_building()
    child = get_test_rental(
        building=building, nickname='Marketing meritocracy')
    parent = get_test_rental(is_combo_of=[child], building=building)
    data = {
        'building': building.pk, 'reports_start_date': '2018-01-01',
        'is_combo_of': []}
    RentalForm(data, instance=child).save()
    self.assertEqual('', child.combo_unit_description)
    data = {
        'building': building.pk, 'reports_start_date': '2018-01-01',
        'is_combo_of': [child.pk]}
    RentalForm(data, instance=parent).save()
    try:
      data = {
          'building': building.pk, 'reports_start_date': '2018-01-01',
          'is_combo_of': [parent.pk]}
      RentalForm(data).save()
      self.fail()
    except ValueError:
      pass
    try:
      data = {
          'building': building.pk, 'reports_start_date': '2018-01-01',
          'is_combo_of': [parent.pk]}
      RentalForm(data, instance=child).save()
      self.fail()
    except ValueError:
      pass
