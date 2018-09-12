from django.conf import settings

from guesty.api_getter import GuestyAPIGetter
from guesty.models import GuestyReservation
from reservations.syncer import GenericSyncer


class Syncer(GenericSyncer):
  def __init__(self, api_getter=GuestyAPIGetter()):
    self.api_getter = api_getter

  def set_id_verified(self, reservation):
    custom_fields = self._get_custom_fields(reservation)
    custom_fields.set_id_verified(True)
    custom_fields.send_changes(self.api_getter)

  def set_phone_email(self, reservation, phone, email):
    custom_fields = self._get_custom_fields(reservation)
    if custom_fields:
      custom_fields.set_email_provided(email)
      custom_fields.set_phone_provided(phone)
      custom_fields.set(
          settings.COMPLETE_ID_VERIFICATION_EMAIL_FIELD_ID, False)
      custom_fields.send_changes(self.api_getter)

  def _get_custom_fields(self, reservation):
    guesty_res = GuestyReservation.objects.get(reservation=reservation)
    return guesty_res.get_custom_fields(self.api_getter)
