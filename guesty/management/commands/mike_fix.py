import sys

from errors.models import log_error
from guesty.api import sync_reservation, get_one, GuestyAPIGetter
from guesty.custom_fields import CustomFields
from guesty.models import GuestyReservation
from reservations.models import Reservation
from util.stayd_command import StaydCommand


TRUE_FIELD_IDS = [
    '5afa2c379ebb42009e34f271',
    '5afec8950c6ec3001f42e5b6',
    '5afec8950c6ec3001f42e5b5',
    '5afec8950c6ec3001f42e5b4',
    '5afec8950c6ec3001f42e5b3',
    '5afec8950c6ec3001f42e5b2',
    '5afec8950c6ec3001f42e5b1',
    '5afa2c379ebb42009e34f26f',
    '5afa2c379ebb42009e34f26e',
    '5b0d6444d8365d002ad94cb7',
    '5afecb67da85ff001f3f10fb',
    '5afa2c379ebb42009e34f26d',
    '5afa2c379ebb42009e34f26c',
    '5afa2c379ebb42009e34f26b',
    '5afa2c379ebb42009e34f26a',
    '5afa2c379ebb42009e34f269']


SPECIFIC_IDS = [
    '5b168599fedfdd001ff0c03e',
    '5af7b37274c9df0061f86baa',
    '5b1685976bb7bb003f97e70e']


class Command(StaydCommand):
  help = 'Mark that the id was verified for every single reservation.'

  def run(self, verbose):
    api_getter = GuestyAPIGetter()
    for guesty_reservation in GuestyReservation.objects.all().order_by(
        '-reservation__check_in'):
      # Issue 2: 'balanceDue' == 0 means paid_in_full == True
      # Issue 3: any reservation imported before June 6th 11:59pm 2018
      # is said to have a valid security deposit.
      try:
        r_long = get_one(Reservation, guesty_reservation.guesty_id)
        reservation = sync_reservation(guesty_reservation.guesty_id)
        print('Syncing reservation {} check_in {}'.format(
            reservation.pk, reservation.check_in))
        r_long = get_one(Reservation, guesty_reservation.guesty_id)
        custom_fields = CustomFields(
            Reservation, guesty_reservation.guesty_id, r_long['customFields'])
        for field_id in TRUE_FIELD_IDS:
          custom_fields.set(field_id, True)
        custom_fields.send_changes(api_getter)
      except Exception:
        message = 'Reservation {} {}'.format(
            guesty_reservation.reservation.pk, guesty_reservation.guesty_id)
        log_error('Error Mike fixing', message, sys.exc_info())

  def name(self):
    return 'verify_all_ids'
