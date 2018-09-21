import re

from util.channels import CHANNELS

DELAY = 'delay'


class TemplateTags(object):
  def get_template_params_for_reservation(self, reservation):
    rental = reservation.rental
    guest = reservation.guest
    first_name = guest.first_name or guest.full_name
    # We wanna keep everything consistent, and we don't control Guesty's
    # template tags, so copy them whenever possible. In some cases I had
    # a name going and we replaced it. I mark the old, still functioning but
    # now undocumented tags with # Legacy.
    return {
        'guest_first_name': first_name,  # Legacy
        'guest_first': first_name,
        'city': reservation.rental.city,  # Legacy
        'listing_address_city': reservation.rental.city,
        'address': reservation.rental.airbnb_address_scrape,  # Legacy
        'listing_address': reservation.rental.airbnb_address_scrape,
        'id_verify_link': reservation.verify_id_url(),
        'guest_email': guest.email or reservation.anonymized_email,
        'checkout_date': reservation.check_out_date_string(),
        'checkout_time': reservation.check_out_time_string(),
        'channel': reservation.channel,
        'checkin_date': reservation.check_in_date_string(),
        'checkin_time': reservation.check_in_time_string(),
        'main_checkin_instructions_link':
            rental.main_checkin_instructions_link,
        'main_property_access_codes_in_order_of_use':
            rental.main_property_access_codes_in_order_of_use,
        'master_access_code_building_door_electronic_lock':
            rental.master_access_code_building_door_electronic_lock,
        'master_access_code_apartment_door_electronic_lock':
            rental.master_access_code_apartment_door_electronic_lock,
        'wifi_network_name':
            rental.wifi_network_name,
        'wifi_password':
            rental.wifi_password,
        'building_trash_instructions':
            rental.building_trash_instructions,
        'link_to_property_page_in_helpdocs':
            rental.link_to_property_page_in_helpdocs,
        'google_maps_link':
            rental.google_maps_link,
        'departure_check_list':
            rental.departure_check_list,
        'local_bag_storage_info':
            rental.local_bag_storage_info,
        'local_bag_storage_link':
            rental.local_bag_storage_link,
        'parking_link':
            rental.parking_link,
        'public_transportation_link':
            rental.public_transportation_link,
        'local_recommendations_link':
            rental.local_recommendations_link,
        'walking_to_nearest_path_stations':
            rental.walking_to_nearest_path_stations,
        'parking_suggestions_no_links':
            rental.parking_suggestions_no_links,
        'public_transport_no_link':
            rental.public_transport_no_link,
        'walk_time_to_nearest_train':
            rental.walk_time_to_nearest_train,
        'laundry_info':
            rental.laundry_info,
        'online_store_available':
            rental.online_store_available}

  def replace_template_tags_for_reservation(self, reservation, on_string):
    tags = self.get_template_params_for_reservation(reservation)
    for tag_name, value in tags.items():
      # online_store_available is a boolean, which doesn't make sense here.
      if value.__class__ is str:
        on_string = self._simple_message_sub(tag_name, value, on_string)

    keep_tag = reservation.channel
    remove_tags = [c.lower() for c in CHANNELS]
    remove_me = keep_tag.lower()
    if remove_me not in remove_tags:
      raise Exception('{} not in {}'.format(remove_me, remove_tags))
    remove_tags.remove(remove_me)

    on_string = re.sub(
        r'{+' + keep_tag + '}+(.+?){+/}+', r'\1', on_string,
        flags=re.IGNORECASE)
    for remove_tag in remove_tags:
      on_string = re.sub(
          r'{+' + remove_tag + '}+.+?{+/}+', '', on_string,
          flags=re.IGNORECASE)
    return on_string

  def _simple_message_sub(self, tag_name, replacement, on_string):
    return re.sub(
        '{+' + tag_name + '}+', replacement, on_string, flags=re.IGNORECASE)
