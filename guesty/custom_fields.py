from django.conf import settings
from djmoney.money import Money

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
  def __init__(self, type_of_thing, guesty_id, custom_fields):
    self.type_of_thing = type_of_thing
    self.guesty_id = guesty_id
    self.custom_fields = custom_fields
    self.changed = False

  """ Reservation fields """
  def sms_enabled(self):
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
  def market_rent(self):
    # Sometimes this returns None for some reason, hence "or 0"
    amount_str = self.get(settings.MARKET_RENT_FIELD_ID, 0) or 0
    return Money(amount_str, 'USD')

  def get(self, key, default):
    for custom_field in self.custom_fields:
      if key == custom_field['fieldId']:
        return custom_field['value']
    return default

  def set(self, field_id, value):
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
