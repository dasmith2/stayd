import copy
import json
from unittest.mock import Mock, call

from work.api import API
from work.api_examples import (
    BOOKING_CREATE, SOURCE_ID_DIDNT_TAKE,
    BOOKING_CREATE_WEBHOOK, ERROR_BOOKING_CREATE_WEBHOOK)
from work.models.booking import Booking
from work.models.raw_event import RawEvent
from work.tests.test_rental import get_test_properly_rental
from rentals.tests import get_test_rental, get_test_building
from reservations.models import Reservation
from reservations.tests import get_test_reservation
from util.random_string import random_string
from util.signals import post_sync
from util.tests import TestCase, FakeResponse
from util.timezone import str_to_tz_dt


def get_test_booking(**kwargs):
  reservation = kwargs.get('reservation', None)
  if not reservation:
    reservation = get_test_reservation(**kwargs)
  rental = kwargs.get('rental', None)
  if not rental:
    rental = reservation.rental
  booking_id = kwargs.get('booking_id', None)
  if not booking_id:
    booking_id = random_string(10)
  return Booking.objects.create(
      booking_id=booking_id,
      reservation=reservation, rental=rental)


class BookingTests(TestCase):
  def test_change_rental(self):
    nnow = str_to_tz_dt('2019-05-13 16:00')
    building = get_test_building()
    old_rental = get_test_rental(building=building, nickname='Old rental')
    get_test_properly_rental(
        source_property_id='candy_weapons',
        properly_property_id='candy_weapons', rental=old_rental)
    reservation = get_test_reservation(
        check_in=str_to_tz_dt('2019-05-15 16:00'),
        check_out=str_to_tz_dt('2019-05-16 11:00'), rental=old_rental)
    get_test_booking(reservation=reservation, booking_id='donut')
    new_rental = get_test_rental(building=building, nickname='New rental')
    get_test_properly_rental(
        source_property_id='rc_car_chase', properly_property_id='rc_car_chase',
        rental=new_rental)
    reservation.rental = new_rental
    reservation.save()
    api = Mock(spec=API)
    api.booking_create.return_value = FakeResponse(True, BOOKING_CREATE)

    post_sync.send(
        sender=Reservation, instance=reservation, api=api, nnow=nnow)

    self.assertEqual([call('donut')], api.booking_cancel.call_args_list)
    Booking.objects.get(reservation=reservation, rental=new_rental)

  def test_booking_create_webhook(self):
    booking = get_test_booking(booking_id='5c34def0aec7992cff0cdbde')
    raw = RawEvent.objects.create(json=json.dumps(BOOKING_CREATE_WEBHOOK))
    api = Mock(spec=API)
    raw.handle(api=api)
    booking.refresh_from_db()
    raw.refresh_from_db()
    self.assertEqual(booking, raw.booking)
    self.assertIsNone(booking.creation_error)
    self.assertIsNotNone(booking.creation_confirmed)

  def test_booking_create_webhook_error(self):
    booking = get_test_booking(booking_id='5c375dac2d7458cfab673035')
    raw = RawEvent.objects.create(
        json=json.dumps(ERROR_BOOKING_CREATE_WEBHOOK))
    api = Mock(spec=API)
    raw.handle(api=api)
    booking.refresh_from_db()
    raw.refresh_from_db()
    self.assertEqual(booking, raw.booking)
    self.assertIsNone(booking.creation_confirmed)
    self.assertEqual(
        'Parameters validation error! (NodeID: 31c40ced612e)',
        booking.creation_error)

  def test_source_property_id_didnt_take(self):
    """ SOURCE_ID_DIDNT_TAKE is an example of what you get back when you try to
    create a booking with a source_property_id that turns out to be invalid.
    """
    rental = get_test_rental()
    # Since the source_property_id is set, as far as we know Properly agrees
    # that's what the source id for that property is on their end.
    get_test_properly_rental(
        source_property_id='NwlTE3dexN', properly_property_id='NwlTE3dexN',
        rental=rental)
    reservation = get_test_reservation(
        rental=rental, channel_id='HMY9N8SZ9P')
    booking = get_test_booking(reservation=reservation)
    dont_delete = get_test_booking()
    self.assertEqual(1, Booking.objects.filter(pk=booking.pk).count())

    api = Mock(spec=API)
    # But wait, curveball, it turns out that when we tried to set the source id
    # for that property it didn't actually take, because properly doesn't know
    # what source property id we're talking about!
    RawEvent.objects.create(
        json=json.dumps(SOURCE_ID_DIDNT_TAKE)).handle(api=api)
    # That's cool, just clear out the source_property_id field so it will
    # re-set, and delete the booking that we THOUGHT we made for that property.
    self.assertEqual(1, len(api.property_update.call_args_list))
    self.assertEqual(0, Booking.objects.filter(pk=booking.pk).count())
    self.assertEqual(1, Booking.objects.filter(pk=dont_delete.pk).count())

  def test_create_booking(self):
    reservation = get_test_reservation(
        channel_id='dubstepper', first_name='Bob',
        last_name='Slob', full_name='Bob Slob',
        check_in=str_to_tz_dt('2018-05-15 16:00'),
        check_out=str_to_tz_dt('2018-05-16 11:00'),
        guest_channel_id='GuestBob')
    get_test_properly_rental(
        rental=reservation.rental, properly_property_id='hippitydoodah',
        source_property_id='hippitydoodah')
    self.assertEqual(
        0, Booking.objects.filter(reservation=reservation).count())
    api = Mock(spec=API)
    api.booking_create.return_value = FakeResponse(True, BOOKING_CREATE)

    post_sync.send(sender=Reservation, instance=reservation, api=api)

    self.assertEqual(
        1, Booking.objects.filter(reservation=reservation).count())
    booking = Booking.objects.get(reservation=reservation)
    self.assertEqual('d8h38hf8h8fh38h83ff3rw', booking.booking_id)
    self.assertEqual(reservation, booking.reservation)
    self.assertEqual('dubstepper', booking.get_source_booking_id())
    expected_data = {
        'sourcePropertyId': 'hippitydoodah',
        'sourceBookingId': 'dubstepper',
        'startDate': '2018-05-15T20:00:00Z',
        'endDate': '2018-05-16T15:00:00Z',
        'title': 'Reservation for Bob Slob',
        'numberOfGuests': 1,
        'guestDetails': [{
            'sourceId': 'GuestBob',
            'firstName': 'Bob',
            'lastName': 'Slob'}]}
    self.assertEqual([call(
        expected_data, print_curl=False)], api.booking_create.call_args_list)

  def test_create_bookings_combo_rentals(self):
    building = get_test_building()
    atom1 = get_test_rental(building=building)
    atom2 = get_test_rental(building=building)
    combo_rental = get_test_rental(
        building=building, is_combo_of=[atom1, atom2])
    get_test_properly_rental(
        source_property_id='OutsmartingYourself',
        properly_property_id='OutsmartingYourself', rental=atom1)
    get_test_properly_rental(
        source_property_id='Humblerella', properly_property_id='Humblerella',
        rental=atom2)
    reservation = get_test_reservation(
        channel_id='IllNeverHaveFunAtPartiesAgain', rental=combo_rental,
        check_in=str_to_tz_dt('2019-01-01 16:00'),
        check_out=str_to_tz_dt('2019-01-02 11:00'))

    api = Mock(spec=API)
    second_booking_create = copy.deepcopy(BOOKING_CREATE)
    second_booking_create['booking.create'][0]['bookingId'] = 'ForRealThisTime'
    api.booking_create.side_effect = [
        FakeResponse(True, BOOKING_CREATE),
        FakeResponse(True, second_booking_create)]

    post_sync.send(sender=Reservation, instance=reservation, api=api)

    self.assertEqual(2, reservation.booking_set.count())
    booking_create_calls = api.booking_create.call_args_list
    self.assertEqual(2, len(booking_create_calls))

    sent_source_booking_ids = set([
        call[0][0]['sourceBookingId'] for call in booking_create_calls])
    expected_source_booking_ids = set([
        'IllNeverHaveFunAtPartiesAgain_{}'.format(atom1.pk),
        'IllNeverHaveFunAtPartiesAgain_{}'.format(atom2.pk)])
    self.assertEqual(expected_source_booking_ids, sent_source_booking_ids)
    reservation.booking_set.get(reservation=reservation, rental=atom1)
    reservation.booking_set.get(reservation=reservation, rental=atom2)
