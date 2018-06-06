from guesty.api import get_one, GuestyAPIGetter
from guesty.custom_fields import CustomFields
from guesty.models import GuestyReservation
from reservations.models import Reservation
from util.stayd_command import StaydCommand


class Command(StaydCommand):
  help = 'Mark that the id was verified for every single reservation.'

  def run(self, verbose):
    api_getter = GuestyAPIGetter()

    for guesty_reservation in GuestyReservation.objects.all():
      r_long = get_one(Reservation, guesty_reservation.guesty_id)
      custom_fields = CustomFields(
          Reservation, r_long['_id'], r_long['customFields'])
      if not custom_fields.id_verified():
        custom_fields.set_id_verified(True)
        custom_fields.send_changes(api_getter)

  def name(self):
    return 'verify_all_ids'
