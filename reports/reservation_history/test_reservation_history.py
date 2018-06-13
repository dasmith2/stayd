from django.test import TestCase

from guests.models import GuestPhoneNumber
from guesty.models import GuestyReservation
from reports.reservation_history.reservation_finder import ReservationFinder
from reservations.tests import get_test_reservation
from util.timezone import tz_dt


class HistoryTests(TestCase):
  def test_find_fields(self):
    get_test_reservation(True)
    reservation = get_test_reservation(
        True,
        channel_reservation_id='1234qwer',
        check_in=tz_dt(2018, 3, 15, 17),
        check_out=tz_dt(2018, 3, 17, 11),
        full_name='Joe Shmoe',
        airbnb_address_scrape='12th hill, Yosemite Park')
    found_reservations = ReservationFinder().find(str(reservation.pk))
    self.assertEqual(1, len(found_reservations))
    found = found_reservations[0]

    self.assertEqual(found.pk, reservation.pk)
    self.assertEqual(
        found.url, '/reports/reservation/{}'.format(reservation.pk))
    self.assertEqual(found.channel_id, '1234qwer')
    self.assertEqual(found.check_in, tz_dt(2018, 3, 15, 17))
    self.assertEqual(found.check_out, tz_dt(2018, 3, 17, 11))
    self.assertEqual(found.full_name, 'Joe Shmoe')
    self.assertEqual(found.address, '12th hill, Yosemite Park')

  def test_find_finding(self):
    get_test_reservation(True)
    reservation = get_test_reservation(
        True,
        channel_reservation_id='oty6a4',
        full_name='Jill Shmill',
        airbnb_address_scrape='14th cave, Yosemite Park')
    get_test_reservation(
        True,
        channel_reservation_id='paaaayui',
        guest=reservation.guest)
    GuestyReservation.objects.create(
        guesty_id='poiuytrewq', reservation=reservation)
    GuestPhoneNumber.objects.create_for_guest(
        reservation.guest, '1(555)666-7777')

    found = ReservationFinder().find('poiuytrewq')
    self.assertEqual(1, len(found))
    self.assertEqual(found[0].channel_id, 'oty6a4')

    found = ReservationFinder().find(
        'https://app.guesty.com/reservations/poiuytrewq/guests')
    self.assertEqual(1, len(found))
    self.assertEqual(found[0].channel_id, 'oty6a4')

    found = ReservationFinder().find('Jill Shmill')
    self.assertEqual(2, len(found))
    channel_ids = sorted([f.channel_id for f in found])
    self.assertEqual(channel_ids, ['oty6a4', 'paaaayui'])

    found = ReservationFinder().find('555-666-7777')
    self.assertEqual(2, len(found))
    channel_ids = sorted([f.channel_id for f in found])
    self.assertEqual(channel_ids, ['oty6a4', 'paaaayui'])

    found = ReservationFinder().find('oty6a4')
    self.assertEqual(1, len(found))
    self.assertEqual(found[0].channel_id, 'oty6a4')

    found = ReservationFinder().find('Nonsense')
    self.assertEqual(0, len(found))
