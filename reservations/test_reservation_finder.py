from util.tests import TestCase

from guests.models import GuestPhoneNumber
from reservations.reservation_finder import ReservationFinder
from reservations.tests import get_test_reservation


class ReservationFinderTests(TestCase):
  def test_find_finding(self):
    get_test_reservation(True)
    reservation = get_test_reservation(
        True,
        channel_reservation_id='oty6a4',
        full_name='Jill Shmill',
        first_name='Jill',
        last_name='Shmill',
        full_address='14th cave, Yosemite Park',
        guesty_id='poiuytrewq')
    get_test_reservation(
        True,
        channel_reservation_id='paaaayui',
        guest=reservation.guest)
    GuestPhoneNumber.objects.create_for_guest(
        reservation.guest, '1(555)666-7777')

    found = ReservationFinder().find('poiuytrewq')
    self.assertEqual(1, len(found))
    self.assertEqual(found[0].channel_reservation_id, 'oty6a4')

    found = ReservationFinder().find(
        'https://app.guesty.com/reservations/poiuytrewq/guests')
    self.assertEqual(1, len(found))
    self.assertEqual(found[0].channel_reservation_id, 'oty6a4')

    found = ReservationFinder().find('jill shmill')
    self.assertEqual(2, len(found))
    channel_ids = sorted([f.channel_reservation_id for f in found])
    self.assertEqual(channel_ids, ['oty6a4', 'paaaayui'])

    found = ReservationFinder().find('jill')
    self.assertEqual(2, len(found))
    channel_ids = sorted([f.channel_reservation_id for f in found])
    self.assertEqual(channel_ids, ['oty6a4', 'paaaayui'])

    found = ReservationFinder().find('shmill')
    self.assertEqual(2, len(found))
    channel_ids = sorted([f.channel_reservation_id for f in found])
    self.assertEqual(channel_ids, ['oty6a4', 'paaaayui'])

    found = ReservationFinder().find('555-666-7777')
    self.assertEqual(2, len(found))
    channel_ids = sorted([f.channel_reservation_id for f in found])
    self.assertEqual(channel_ids, ['oty6a4', 'paaaayui'])

    found = ReservationFinder().find('oty6a4')
    self.assertEqual(1, len(found))
    self.assertEqual(found[0].channel_reservation_id, 'oty6a4')

    found = ReservationFinder().find('Nonsense')
    self.assertEqual(0, len(found))
