from django.conf import settings

from rentals.models import Rental
from reservations.models import Reservation


class CustomFields(object):
  """ The custom fields on Guesty reservations and guesty listings (a.k.a
  rentals) are complicated enough to get their own class and everything.
  custom_fields is, like,
  [{'fieldId': '5afa2c379ebb42009e34f270', 'value': True,
  '_id': '5afc7708bbf3af002af8f0c9'}] _id is useless here.

  The GUESTY_MESSAGE_TOGGLE_CUSTOM_FIELDS list is in guest_messages/models.py
  There's another list in stayd/settings.py
  """
  def __init__(self, type_of_thing, guesty_id, custom_fields=None):
    self.type_of_thing = type_of_thing
    self.guesty_id = guesty_id
    self.custom_fields = custom_fields
    self.changed = False

  def download_custom_fields(self):
    from guesty.api import get_one
    self.custom_fields = get_one(
        self.type_of_thing, self.guesty_id)['customFields']
    return self.custom_fields

  def get(self, key, default):
    self._check_custom_fields_exists()
    for custom_field in self.custom_fields:
      if key == custom_field['fieldId']:
        return custom_field['value']
    return default

  def set(self, field_id, value):
    self._check_custom_fields_exists()
    # I tried, and unfortunately you can't just
    # self.api_getter.put('reservations/{}'.format(reservation_id), {
    #     "customFields": [{"fieldId": field_id, "value": value}]})
    # because that wipes out all the other custom fields.
    # Let's make an assumption here that set is called when values change.
    # Therefore, don't bother to look up what the current value is and
    # see if it changed (that would require knowing the default, so it gets
    # complicated). Rather, just trust that when this is being called, things
    # are changing.
    self.changed = True

    existed_already = False
    for field in self.custom_fields:
      if field['fieldId'] == field_id:
        existed_already = True
        field['value'] = value
    if not existed_already:
      self.custom_fields.append({'fieldId': field_id, 'value': value})

  def send_changes(self, api_getter):
    self._check_custom_fields_exists()
    if self.type_of_thing is Rental:
      url_start = 'listings'
    elif self.type_of_thing is Reservation:
      url_start = 'reservations'
    else:
      raise Exception(self.type_of_thing)
    if self.changed:
      url = '{}/{}'.format(url_start, self.guesty_id)
      data = {"customFields": self.custom_fields}
      api_getter.put(url, data)

  def _check_custom_fields_exists(self):
    if self.custom_fields is None:
      raise Exception(
          'You must either pass the custom_fields in the constructor '
          'or download them')

  """ Reservation fields """
  def trust_me_cc_authorized(self):
    return self.get(settings.TRUST_ME_CC_AUTHORIZED, False)

  def messages_enabled(self):
    return self.get(settings.ALL_AUTOMATIONS_FIELD_ID, True)

  def id_verified(self):
    return self.get(settings.ID_VERIFIED_FIELD_ID, False)

  def set_id_verified(self, value):
    return self.set(settings.ID_VERIFIED_FIELD_ID, value)

  def email_provided(self):
    return self.get(settings.EMAIL_PROVIDED_FIELD_ID, '')

  def set_email_provided(self, value):
    return self.set(settings.EMAIL_PROVIDED_FIELD_ID, value)

  def phone_provided(self):
    return self.get(settings.PHONE_PROVIDED_FIELD_ID, None)

  def set_phone_provided(self, value):
    return self.set(settings.PHONE_PROVIDED_FIELD_ID, value)

  def paid_in_full(self):
    return self.get(settings.PAID_IN_FULL_FIELD_ID, False)

  def set_paid_in_full(self, value):
    return self.set(settings.PAID_IN_FULL_FIELD_ID, value)

  def credit_card_authorization_valid(self):
    return self.get(settings.CREDIT_CARD_AUTHORIZATION_VALID_FIELD_ID, False)

  def set_credit_card_authorization_valid(self, value):
    return self.set(settings.CREDIT_CARD_AUTHORIZATION_VALID_FIELD_ID, value)

  """ Rental fields (listing fields in Guesty terminology) """
  def set_main_checkin_instructions_link(self, value):
    return self.set('5af745460b3bdc0026497c02', value)

  def main_checkin_instructions_link(self):
    return self.get('5af745460b3bdc0026497c02', '')

  def set_main_property_access_codes_in_order_of_use(self, value):
    return self.set('5b18152f521f55001fdaada2', value)

  def main_property_access_codes_in_order_of_use(self):
    return self.get('5b18152f521f55001fdaada2', '')

  def set_master_access_code_building_door_electronic_lock(self, value):
    return self.set('5af73c2390fe68001faea7f4', value)

  def master_access_code_building_door_electronic_lock(self):
    return self.get('5af73c2390fe68001faea7f4', '')

  def set_master_access_code_apartment_door_electronic_lock(self, value):
    return self.set('5af73c2390fe68001faea7f3', value)

  def master_access_code_apartment_door_electronic_lock(self):
    return self.get('5af73c2390fe68001faea7f3', '')

  def set_wifi_network_name(self, value):
    return self.set('5af73c2390fe68001faea7f5', value)

  def wifi_network_name(self):
    return self.get('5af73c2390fe68001faea7f5', '')

  def set_wifi_password(self, value):
    return self.set('5b055eaabd27a0005d6dd505', value)

  def wifi_password(self):
    return self.get('5b055eaabd27a0005d6dd505', '')

  def set_building_trash_instructions(self, value):
    return self.set('5af745460b3bdc0026497c00', value)

  def building_trash_instructions(self):
    return self.get('5af745460b3bdc0026497c00', '')

  def set_link_to_property_page_in_helpdocs(self, value):
    return self.set('5af9e93c9ebb42009e34c5d5', value)

  def link_to_property_page_in_helpdocs(self):
    return self.get('5af9e93c9ebb42009e34c5d5', '')

  def set_google_maps_link(self, value):
    return self.set('5b033afac863bf0024bd7f20', value)

  def google_maps_link(self):
    return self.get('5b033afac863bf0024bd7f20', '')

  def set_departure_check_list(self, value):
    return self.set('5b033afac863bf0024bd7f1f', value)

  def departure_check_list(self):
    return self.get('5b033afac863bf0024bd7f1f', '')

  def set_local_bag_storage_info(self, value):
    return self.set('5b033b855751bf001f6711f2', value)

  def local_bag_storage_info(self):
    return self.get('5b033b855751bf001f6711f2', '')

  def set_local_bag_storage_link(self, value):
    return self.set('5b1543a897e469001f7b9ced', value)

  def local_bag_storage_link(self):
    return self.get('5b1543a897e469001f7b9ced', '')

  def set_parking_link(self, value):
    return self.set('5b034704363df8002635081a', value)

  def parking_link(self):
    return self.get('5b034704363df8002635081a', '')

  def set_public_transportation_link(self, value):
    return self.set('5b152bc2be79aa001f06660e', value)

  def public_transportation_link(self):
    return self.get('5b152bc2be79aa001f06660e', '')

  def set_local_recommendations_link(self, value):
    return self.set('5b034746a04aba002499e22d', value)

  def local_recommendations_link(self):
    return self.get('5b034746a04aba002499e22d', '')

  def set_walking_to_nearest_path_stations(self, value):
    return self.set('5b180a2ef2ab54001fe5dfb4', value)

  def walking_to_nearest_path_stations(self):
    return self.get('5b180a2ef2ab54001fe5dfb4', '')

  def set_parking_suggestions_no_links(self, value):
    return self.set('5b180bca47b570002af67404', value)

  def parking_suggestions_no_links(self):
    return self.get('5b180bca47b570002af67404', '')

  def set_public_transport_no_link(self, value):
    return self.set('5b1fc63e59414f0020df6a33', value)

  def public_transport_no_link(self):
    return self.get('5b1fc63e59414f0020df6a33', '')

  def set_walk_time_to_nearest_train(self, value):
    return self.set('5b2436d7c116f50175c42ebf', value)

  def walk_time_to_nearest_train(self):
    return self.get('5b2436d7c116f50175c42ebf', '')

  def set_laundry_info(self, value):
    return self.set('5b243881a3861b02660d9b26', value)

  def laundry_info(self):
    return self.get('5b243881a3861b02660d9b26', '')

  def set_online_store_available(self, value):
    return self.set('5ba51973a264260045dab949', value)

  def online_store_available(self):
    return self.get('5ba51973a264260045dab949', False)
