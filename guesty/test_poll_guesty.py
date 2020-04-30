from django.test import TestCase

from guesty.models import ReservedReservation
from guesty.poll_guesty import poll_reserved_reservations
from reservations.models import Reservation
from reservations.tests import get_test_reservation


class PollReservedTests(TestCase):
  def test_poll_reserved_reservations(self):
    ReservedReservation.objects.create(guesty_id='asdf')
    ReservedReservation.objects.create(guesty_id='qwer')

    class TestAPI():
      def get_one(self, klass, guesty_id):
        if klass != Reservation:
          raise Exception(klass)
        if guesty_id == 'asdf':
          return {'status': 'confirmed'}
        elif guesty_id == 'qwer':
          return {'status': 'reserved'}
        raise Exception(guesty_id)

    def use_sync_reservation(guesty_id):
      if guesty_id == 'asdf':
        return get_test_reservation(status='confirmed', guesty_id='asdf')
      raise Exception(guesty_id)
    poll_reserved_reservations(
        api=TestAPI(), use_sync_reservation=use_sync_reservation)
    self.assertFalse(
        ReservedReservation.objects.filter(guesty_id='asdf').exists())
    self.assertTrue(
        ReservedReservation.objects.filter(guesty_id='qwer').exists())
