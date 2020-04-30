from guest_messages.models.email import Email
from guest_messages.models.sms import SMS
from guesty.api import GuestyAPI
from guesty.custom_field_ids import (
    GUESTY_MESSAGE_TOGGLE_CUSTOM_FIELDS, ID_VERIFIED_FIELD_ID,
    RISK_SCORE_FIELD_ID, EMAIL_PROVIDED_FIELD_ID, PHONE_PROVIDED_FIELD_ID,
    PAID_IN_FULL_FIELD_ID, CREDIT_CARD_AUTHORIZATION_VALID_FIELD_ID,
    GUEST_FEEDBACK_FORM_LINK_FIELD_ID, ID_VERIFICATION_LINK_FIELD_ID,
    IS_TEST_RESERVATION_FIELD_ID, ENTER_1_TO_ACTIVATE_LISTING_IN_KEYS,
    TRUST_ME_CC_AUTHORIZED, CANARY_IN_THE_COALMINE_FIELD_ID,
    DEFAULT_GUESTY_FLAG_VALUE, CHECKIN_INSTRUCTIONS_EMAIL,
    SMS_CONFIRMING_GUEST_RECEIVED_INSTRUCTIONS, DAY_OF_CHECKIN_SMS,
    HOWS_EVERYTHING_SMS, CHECKOUT_INSTRUCTIONS_EMAIL, MORNING_OF_CHECKOUT_SMS,
    FEEDBACK_REQUEST_SMS, NPS_RATE_US_EMAIL,
    MESSAGE_WHEN_GUEST_BOOKS, REQUEST_TO_COMPLETE_ID_EMAIL,
    REQUEST_TO_COMPLETE_ID_SMS, REMINDER_TO_COMPLETE_ID_SMS)
from id_verify.models import Submission
from rentals.models import Rental
from reservations.models import Reservation


def turn_on_boolean_custom_field_for_all_existing_reservations(
    custom_field_id, only_guesty_id=None):
  """ You have to do this for any new boolean custom field you want to default
  to True. This happens whenever we introduce a new email or sms that we wish
  to be able to turn off with a guesty boolean custom field. """
  reservations = Reservation.objects.filter(
      guestyreservation__isnull=False)
  if only_guesty_id:
    reservations = reservations.filter(
        guestyreservation__guesty_id=only_guesty_id)
  for reservation in reservations:
    custom_fields = CustomFields(
        Reservation, reservation.guestyreservation.guesty_id)
    custom_fields.download_custom_fields()
    custom_fields.set(custom_field_id, True)
    custom_fields.send_changes(GuestyAPI())


class CustomFields(object):
  """ The custom fields on Guesty reservations and guesty listings (a.k.a
  rentals) are complicated enough to get their own class and everything.
  custom_fields is, like,
  [{'fieldId': '5afa2c379ebb42009e34f270', 'value': True,
  '_id': '5afc7708bbf3af002af8f0c9'}] _id is useless here.
  """
  def __init__(self, type_of_thing, guesty_id, custom_fields=None, api=None):
    self.type_of_thing = type_of_thing
    self.guesty_id = guesty_id
    self.custom_fields = custom_fields
    self.changed = False
    self.api = api or GuestyAPI()

  def download_custom_fields(self):
    from guesty.guesty import get_one
    self.custom_fields = get_one(
        self.type_of_thing, self.guesty_id)['customFields']
    return self.custom_fields

  def send_changes(self, api):
    self._check_custom_fields_exists()
    if self.type_of_thing is Rental:
      url_start = 'listings'
    elif self.type_of_thing is Reservation:
      url_start = 'reservations'
    else:
      raise Exception(self.type_of_thing)
    if self.changed:
      url = '{}/{}'.format(url_start, self.guesty_id)
      data = {'customFields': self.custom_fields}
      api.put(url, data)

  def get(self, key, default):
    self._check_custom_fields_exists()
    for custom_field in self.custom_fields:
      if key == custom_field['fieldId']:
        return custom_field['value']
    return default

  def set(self, field_id, value):
    self._check_custom_fields_exists()
    # I tried, and unfortunately you can't just
    # self.api.put('reservations/{}'.format(reservation_id), {
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

  def _check_custom_fields_exists(self):
    if self.custom_fields is None:
      raise Exception(
          'You must either pass the custom_fields in the constructor '
          'or download them')

  def turn_on_for_imported_reservation(self, api):
    """ When we import new units on Guesty, the initial import has all the
    custom fields turned off and the id not verified. But we want to just allow
    all those existing reservations. """
    self.set_canary_in_the_coalmine()
    self.set_id_verified(True)

    for custom_id in [
        CHECKIN_INSTRUCTIONS_EMAIL, SMS_CONFIRMING_GUEST_RECEIVED_INSTRUCTIONS,
        DAY_OF_CHECKIN_SMS, HOWS_EVERYTHING_SMS, CHECKOUT_INSTRUCTIONS_EMAIL,
        MORNING_OF_CHECKOUT_SMS, FEEDBACK_REQUEST_SMS, NPS_RATE_US_EMAIL]:
      self.set(custom_id, True)

    for custom_id in [
        MESSAGE_WHEN_GUEST_BOOKS, REQUEST_TO_COMPLETE_ID_EMAIL,
        REQUEST_TO_COMPLETE_ID_SMS, REMINDER_TO_COMPLETE_ID_SMS]:
      self.set(custom_id, False)

    self.send_changes(api)

  def handle_message_custom_fields(self, reservation):
    smss = SMS.objects.get_for_reservation(reservation)
    emails = Email.objects.get_for_reservation(reservation)
    messages = list(smss) + list(emails)

    for message in messages:
      guesty_custom_field_id = message.guesty_custom_field_id()
      if guesty_custom_field_id:
        specific_enabled = self.get(
            message.guesty_custom_field_id(),
            # This has to stay False! I'm sorry! See the explanation on
            # DEFAULT_GUESTY_FLAG_VALUE for details on this sorry affair.
            DEFAULT_GUESTY_FLAG_VALUE)
        if message.green_light != specific_enabled:
          message.green_light = specific_enabled
          message.save()

  def pull_custom_fields(self, reservation):
    if reservation.is_test_reservation != self.is_test_reservation():
      reservation.is_test_reservation = self.is_test_reservation()
      reservation.save()
    # Sometimes VAs accidentally turn off id_verified. id_verified is only
    # turn-onable.
    if self.id_verified() and not reservation.id_verified:
      reservation.id_verified = self.id_verified()
      reservation.save()
    if reservation.guest.email != self.email_provided():
      reservation.guest.email = self.email_provided()
      reservation.guest.save()
    provided_phone = self.phone_provided()
    if provided_phone and reservation.guest.phone != provided_phone:
      reservation.guest.set_primary_phone(provided_phone)
    self.handle_message_custom_fields(reservation)

  def push_custom_fields(self, reservation):
    if self.paid_in_full() != reservation.is_paid_in():
      self.set_paid_in_full(reservation.is_paid_in())
    has_deposit = reservation.has_security_deposit()
    if self.credit_card_authorization_valid() != has_deposit:
      self.set_credit_card_authorization_valid(has_deposit)
    feedback_link = reservation.get_guest_feedback_form_link()
    if self.guest_feedback_form_link() != feedback_link:
      self.set_guest_feedback_form_link(feedback_link)
    id_verify_link = reservation.verify_id_url()
    if self.id_verification_link() != id_verify_link:
      self.set_id_verification_link(id_verify_link)
    # Every once and a while id_verified gets turned off inexpclicably. As we
    # can't think of a case where you'd want to turn off id_verified on a
    # reservation with a legit verification, we'll just make it impossible to
    # permanently turn off id_verified when it's indeed verified. Note that
    # there ARE cases you'd manually turn on id_verified even without a valid
    # submission. That happens if id_verification goes down and the VAs have
    # the guest just text them photos or something.
    id_verified = Submission.objects.all_good(reservation)
    if id_verified and not self.id_verified():
      self.set_id_verified(True)

    # Guesty's solution to default values in boolean custom fields is to, like,
    # wait a moment and THEN switch them all on in a second webhook. Since we
    # respond to the first webhook, that causes a third webhook where they're
    # all switched off again. Confused? Exactly. Guesty's handling of boolean
    # custom fields is complicated and error prone. Anyway, point is, if the
    # canary is dead, roll our eyes and turn them all back on again.
    if not self.canary_in_the_coalmine():
      self.set_canary_in_the_coalmine()
      for field_id, name in GUESTY_MESSAGE_TOGGLE_CUSTOM_FIELDS:
        self.set(field_id, True)

    self.send_changes(self.api)

  """ Reservation fields """
  def trust_me_cc_authorized(self):
    return self.get(TRUST_ME_CC_AUTHORIZED, False)

  def set_trust_me_cc_authorized(self):
    return self.set(TRUST_ME_CC_AUTHORIZED, True)

  def canary_in_the_coalmine(self):
    return self.get(
        CANARY_IN_THE_COALMINE_FIELD_ID,
        DEFAULT_GUESTY_FLAG_VALUE)

  def set_canary_in_the_coalmine(self):
    return self.set(CANARY_IN_THE_COALMINE_FIELD_ID, True)

  def id_verified(self):
    return self.get(ID_VERIFIED_FIELD_ID, False)

  def set_id_verified(self, value):
    return self.set(ID_VERIFIED_FIELD_ID, value)

  def risk_score(self):
    return self.get(RISK_SCORE_FIELD_ID, None)

  def set_risk_score(self, risk_score):
    return self.set(RISK_SCORE_FIELD_ID, risk_score)

  def email_provided(self):
    return self.get(EMAIL_PROVIDED_FIELD_ID, '')

  def set_email_provided(self, value):
    return self.set(EMAIL_PROVIDED_FIELD_ID, value)

  def phone_provided(self):
    return self.get(PHONE_PROVIDED_FIELD_ID, None)

  def set_phone_provided(self, value):
    return self.set(PHONE_PROVIDED_FIELD_ID, value)

  def paid_in_full(self):
    return self.get(PAID_IN_FULL_FIELD_ID, False)

  def set_paid_in_full(self, value):
    return self.set(PAID_IN_FULL_FIELD_ID, value)

  def credit_card_authorization_valid(self):
    return self.get(CREDIT_CARD_AUTHORIZATION_VALID_FIELD_ID, False)

  def set_credit_card_authorization_valid(self, value):
    return self.set(CREDIT_CARD_AUTHORIZATION_VALID_FIELD_ID, value)

  def guest_feedback_form_link(self):
    return self.get(GUEST_FEEDBACK_FORM_LINK_FIELD_ID, '')

  def set_guest_feedback_form_link(self, value):
    return self.set(GUEST_FEEDBACK_FORM_LINK_FIELD_ID, value)

  def id_verification_link(self):
    return self.get(ID_VERIFICATION_LINK_FIELD_ID, '')

  def set_id_verification_link(self, value):
    return self.set(ID_VERIFICATION_LINK_FIELD_ID, value)

  def is_test_reservation(self):
    return self.get(IS_TEST_RESERVATION_FIELD_ID, False)

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

  def backup_check_in_codes(self):
    return self.get('5af73c2390fe68001faea7f0', '')

  def backup_check_in_instructions_link(self):
    return self.get('5af745460b3bdc0026497c01', '')

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

  def set_is_test_rental(self, value):
    return self.set('5c1a84d8d548c100211f21e5', value)

  def is_test_rental(self):
    return self.get('5c1a84d8d548c100211f21e5', False)

  def extra_details(self):
    return self.get('5cf19848e5f880002112cf54', '')

  def enter_1_to_activate_listing_in_keys(self):
    return self.get(ENTER_1_TO_ACTIVATE_LISTING_IN_KEYS, '')

  def set_enter_1_to_activate_listing_in_keys(self, value):
    return self.set(ENTER_1_TO_ACTIVATE_LISTING_IN_KEYS, value)

  def leave_the_keys(self):
    return self.get('5d64197c7ca527001ffa6016', '')
