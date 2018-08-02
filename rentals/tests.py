from djmoney.money import Money

from rentals.models import Rental, Owner, Airvatar


def get_test_owner(create, **kwargs):
  owner = Owner(
      name=kwargs.get('name', 'The queen of England'),
      email=kwargs.get('email', 'thequeenofengland@gmail.com'))
  if create:
    owner.save()
  return owner


def get_test_rental(create, **kwargs):
  owner = get_test_owner(create, **kwargs)
  airvatar = get_test_airvatar(create, **kwargs)
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
      airvatar=kwargs.get('airvatar', airvatar),
      nickname=kwargs.get('nickname', '254 Penwipper, Bismund'),
      market_rent=kwargs.get('market_rent', Money(1500, 'USD')),
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
          'laundry_info', ''))
  if create:
    rental.save()
  return rental


def get_test_airvatar(create, **kwargs):
  # Airvatars should definitely be in place already, so by default let's
  # return saved ones.
  name = kwargs.get('airvatar_name', 'Ron Burgundy')
  airvatars = Airvatar.objects.filter(name=name)
  if len(airvatars):
    return airvatars[0]
  airvatar = Airvatar(
      name=name,
      ip=kwargs.get('ip', '127.0.0.1'),
      port=kwargs.get('port', '123456'),
      gmail_address=kwargs.get('gmail_address', 'ron_burgundy@gmail.com'),
      gmail_password=kwargs.get('gmail_password', 'thatescalatedquickly'),
      airbnb_password=kwargs.get('airbnb_password', 'imnotevenmad'),
      front_channel=kwargs.get('front_channel', 'cha_637r'))
  if create:
    airvatar.save()
  return airvatar
