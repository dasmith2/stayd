from django.conf import settings


class CustomFields(object):
  """ The custom fields on Guesty reservations are complicated enough to
  get their own class and everything. The custom_fields... field is, like,
  [{'fieldId': '5afa2c379ebb42009e34f270', 'value': True,
  '_id': '5afc7708bbf3af002af8f0c9'}] _id is useless here. We want
  admins to be able to turn off specific automatic smss, or all of them,
  from Guesty. """
  def __init__(self, reservation, guesty_reservation_id, custom_fields):
      self.reservation = reservation
      self.guesty_reservation_id = guesty_reservation_id
      self.custom_fields = custom_fields
      self.changed = False

  def sms_enabled(self):
    return self.get(settings.ALL_AUTOMATIONS_FIELD_ID, True)

  def temporary_allow_sms(self):
    return self.get(settings.TEMPORARY_ALLOW_SMS, False)

  def id_verified(self):
    return self.get(settings.ID_VERIFIED_FIELD_ID, False)

  def email_provided(self):
    return self.get(settings.EMAIL_PROVIDED_FIELD_ID, '')

  def phone_provided(self):
    return self.get(settings.PHONE_PROVIDED_FIELD_ID, None)

  def paid_in_full(self):
    return self.get(settings.PAID_IN_FULL_FIELD_ID, False)

  def set_paid_in_full(self, value):
    return self.set(settings.PAID_IN_FULL_FIELD_ID, value)

  def credit_card_authorization_valid(self):
    return self.get(settings.CREDIT_CARD_AUTHORIZATION_VALID_FIELD_ID, False)

  def set_credit_card_authorization_valid(self, value):
    return self.set(settings.CREDIT_CARD_AUTHORIZATION_VALID_FIELD_ID, value)

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
    if self.changed:
      api_getter.put('reservations/{}'.format(self.guesty_reservation_id), {
          "customFields": self.custom_fields})
