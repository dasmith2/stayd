from datetime import date

from django.contrib.auth.models import User
from djmoney.money import Money

from rentals.models import Rental, MonthlyExpense, RENT
from util.tests import TestCase


def get_test_monthly_expense(create, **kwargs):
  default_rental = None
  if 'rental' not in kwargs:
    default_rental = get_test_rental(create, **kwargs)
  monthly_expense = MonthlyExpense(
      rental=kwargs.get('rental', default_rental),
      start_date=kwargs.get('start_date', date(2017, 1, 1)),
      monthly_amount=kwargs.get('monthly_amount', Money(365 * 5, 'USD')),
      kind=kwargs.get('kind', RENT))
  if create:
    monthly_expense.save()
  return monthly_expense


def get_test_owner(create, **kwargs):
  if 'name' in kwargs:
    raise Exception(
        'name isn\'t valid for this any more. You need first and last.')
  username = kwargs.get('username', 'thequeenofengland')
  existing = User.objects.filter(username=username).first()
  if existing:
    return existing
  owner = User(
      username=username,
      first_name=kwargs.get('first_name', 'The queen'),
      last_name=kwargs.get('last_name', 'of England'),
      email=kwargs.get('email', 'thequeenofengland@gmail.com'))
  if create:
    owner.save()
  return owner


def get_test_rental(create, **kwargs):
  owner = get_test_owner(create, **kwargs)
  rental = Rental(
      airbnb_address_scrape=kwargs.get(
          'airbnb_address_scrape', '254 Penwipper Dr., Bismund, Montana'),
      city=kwargs.get('city', 'Bismund'),
      time_zone=kwargs.get('time_zone', 'US/Central'),
      currency=kwargs.get('currency', 'USD'),
      accommodates=kwargs.get('accommodates', 2),
      bathrooms=kwargs.get('bathrooms', 1),
      bedrooms=kwargs.get('bedrooms', 1),
      property_type=kwargs.get('property_type', 'Apartment'),
      room_type=kwargs.get('room_type', 'Entire home/apt'),
      owner=kwargs.get('owner', owner),
      nickname=kwargs.get('nickname', '254 Penwipper, Bismund'),
      is_active=kwargs.get('is_active', True),
      main_checkin_instructions_link=kwargs.get(
          'main_checkin_instructions_link', ''),
      main_property_access_codes_in_order_of_use=kwargs.get(
          'main_property_access_codes_in_order_of_use', ''),
      master_access_code_building_door_electronic_lock=kwargs.get(
          'master_access_code_building_door_electronic_lock', ''),
      master_access_code_apartment_door_electronic_lock=kwargs.get(
          'master_access_code_apartment_door_electronic_lock', ''),
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
          'online_store_available', False))
  if create:
    rental.save()
  return rental


class RentalTests(TestCase):
  def test_pro_rated_rent(self):
    rental = get_test_rental(True)
    get_test_monthly_expense(
        True, rental=rental, start_date=date(2017, 1, 15),
        monthly_amount=Money(365, 'USD'), kind=RENT)
    get_test_monthly_expense(
        True, rental=rental, start_date=date(2017, 1, 16),
        monthly_amount=Money(365 * 2, 'USD'), kind=RENT)
    get_test_monthly_expense(
        True, rental=rental, start_date=date(2017, 1, 17),
        monthly_amount=Money(1000000, 'USD'), kind=RENT)
    get_test_monthly_expense(
        True, rental=rental, start_date=date(2017, 1, 18),
        monthly_amount=Money(1000000, 'USD'), kind=RENT)

    from stats.models.stale import Stale
    Stale.objects.fix()

    self.assertEqual(
        Money(36, 'USD'),
        rental.pro_rated_rent(date(2017, 1, 1), date(2017, 1, 17)))
