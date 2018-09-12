import copy
from datetime import time, timedelta
import json
import pprint
from unittest.mock import Mock, call

from django.conf import settings
from util.tests import TestCase
from django.utils.dateparse import parse_datetime
from django.utils.timezone import make_aware, now
from djmoney.money import Money

from errors.models import ErrorLogger
from guest_messages.models.models_base import DAYS, AFTER, CHECKIN
from guest_messages.tests import get_test_smstemplate, SMS
from guests.models import Guest, GuestPhoneNumber
from guesty.api import GuestySync, GuestyAPIGetter
from guesty.api_examples import (
    GUEST, RENTAL, RESERVATION, RESERVATION_FOR_LIST, NO_BALANCE_DUE_MONEY,
    REFUND_NO_BALANCE_DUE_MONEY)
from guesty.custom_fields import CustomFields
from guesty.models import (
    GuestyReservation, GuestyRental, GuestyGuest, RawEvent)
from rentals.models import Rental
from rentals.tests import get_test_rental
from reservations.models import Reservation
from reservations.tests import get_test_reservation
from util.channels import BOOKINGCOM
from util.timezone import morning_from_date, afternoon_from_date


class MockGuestyAPIGetter(object):
  """ We should look into replacing this with Mock(spec=GuestyAPIGetter)
  because that will fail properly if the function names change,
  and it will reduce custom stuff in our tests. """
  def __init__(self):
    self.address = None
    self.guesty_rental_id = None
    self.check_out = None
    self.check_in = None

  def get_one(self, type_of_thing, guesty_id):
    if type_of_thing is Guest:
      to_return = GUEST
    elif type_of_thing is Reservation:
      to_return = RESERVATION
      if self.check_out:
        to_return['checkOut'] = self.check_out.isoformat()
      if self.check_in:
        to_return['checkIn'] = self.check_in.isoformat()
    elif type_of_thing is Rental:
      to_return = RENTAL
    else:
      raise Exception('Not sure what to do with a {}'.format(type_of_thing))
    if to_return['_id'] != guesty_id:
      raise Exception(
          'Asked for {} {} but what I have is {} {}'.format(
              type_of_thing, guesty_id, type_of_thing, to_return['_id']))
    return to_return

  def get_many(self, type_of_thing, skip, limit, from_date=None, to_date=None):
    if from_date or to_date:
      raise Exception(
          'from_date and to_date are just for messing around in the shell.')
    if skip > 0:
      return []
    if type_of_thing is Rental:
      rental_long = copy.deepcopy(RENTAL)
      if self.address:
        rental_long['address']['full'] = self.address
      if self.guesty_rental_id:
        rental_long['_id'] = self.guesty_rental_id
      return [rental_long]
    elif type_of_thing is Reservation:
      return [RESERVATION_FOR_LIST]
    raise Exception('Not sure what to do with a {}'.format(type_of_thing))

  def set_address(self, address):
    self.address = address

  def set_guesty_rental_id(self, guesty_rental_id):
    self.guesty_rental_id = guesty_rental_id

  def set_check_in(self, check_in):
    self.check_in = check_in

  def set_check_out(self, check_out):
    self.check_out = check_out

  def put(self, *kwargs):
    pass


class WebhookAPIGetter(object):
  def __init__(self):
    self.webhooks = [{
        'accountId': 'existingAccount1',
        'events': ['existing.event1'],
        'url': 'https://a.com/guesty_webhook/existing.event1'}, {
        '_id': 'bbbbbb',
        'accountId': 'missingAccount',
        'events': ['existing.event1'],
        'url': 'https://a.com/guesty_webhook/existing.event1'}, {
        '_id': 'cccccc',
        'accountId': 'existingAccount1',
        'events': ['missing.event'],
        'url': 'https://a.com/guesty_webhook/missing.event'}, {
        '_id': 'dddddd',
        'accountId': 'missingAccount',
        'events': ['missing.event'],
        'url': 'https://other_server.com/guesty_webhook/missing.event'}, {
        '_id': 'eeeeee',
        'accountId': 'existingAccount2',
        'events': ['existing.event2'],
        'url': 'https://other_server.com/guesty_webhook/existing.event2'}]

  def get_all(self, type_of_thing):
    if type_of_thing is Rental:
      return [{'accountId': 'existingAccount1'}] * 25 + [
          {'accountId': 'existingAccount2'}]
    elif type_of_thing == 'Webhook':
      return list(self.webhooks)
    else:
      raise Exception(type_of_thing)

  def post(self, url, data):
    if url != 'webhooks':
      raise Exception(url)
    self.webhooks.append(data)

  def delete(self, url):
    parts = url.split('/')
    if parts[0] != 'webhooks':
      raise Exception(parts[0])
    for hook in self.webhooks:
      if hook.get('_id', '') == parts[1]:
        self.webhooks.remove(hook)
        return
    raise Exception(url)


class WebhookTests(TestCase):
  def test_sync_webhooks(self):
    api_getter = WebhookAPIGetter()
    GuestySync(api_getter).sync_webhooks(
        'https://a.com/', events=['existing.event1', 'existing.event2'])
    expected = [{
        'accountId': 'existingAccount1',
        'events': ['existing.event1'],
        'url': 'https://a.com/guesty_webhook/existing.event1'}, {
        '_id': 'dddddd',
        'accountId': 'missingAccount',
        'events': ['missing.event'],
        'url': 'https://other_server.com/guesty_webhook/missing.event'}, {
        '_id': 'eeeeee',
        'accountId': 'existingAccount2',
        'events': ['existing.event2'],
        'url': 'https://other_server.com/guesty_webhook/existing.event2'}, {
        'accountId': 'existingAccount2',
        'events': ['existing.event1'],
        'url': 'https://a.com/guesty_webhook/existing.event1'}, {
        'accountId': 'existingAccount2',
        'events': ['existing.event2'],
        'url': 'https://a.com/guesty_webhook/existing.event2'}, {
        'accountId': 'existingAccount1',
        'events': ['existing.event2'],
        'url': 'https://a.com/guesty_webhook/existing.event2'}]
    equal = len(expected) == len(api_getter.webhooks) and all(
        e in api_getter.webhooks for e in expected)
    if not equal:
      pper = pprint.PrettyPrinter()
      print('The Webhooks test is about to fail. Expected:')
      pper.pprint(expected)
      print('Got:')
      pper.pprint(api_getter.webhooks)
    self.assertTrue(equal)


class RentalTests(TestCase):
  def test_sync_rentals(self):
    mock_getter = MockGuestyAPIGetter()
    mock_getter.set_address('221b Baker St., London, UK')
    mock_getter.set_guesty_rental_id('5e5e5e')

    self.assertEqual(0, Rental.objects.filter(
        airbnb_address_scrape='221b Baker St., London, UK').count())

    GuestySync(mock_getter).sync_rentals()
    GuestySync(mock_getter).sync_rentals()

    self.assertEqual(1, Rental.objects.filter(
        airbnb_address_scrape='221b Baker St., London, UK').count())

    rental = GuestyRental.objects.filter(guesty_id='5e5e5e').first().rental

    self.assertEqual(
        rental.airbnb_address_scrape, '221b Baker St., London, UK')
    self.assertEqual(rental.time_zone, 'America/New_York')
    self.assertEqual(rental.currency, 'BZD')
    self.assertEqual(rental.accommodates, 10)
    self.assertEqual(rental.bathrooms, 2)
    self.assertEqual(rental.bedrooms, 3)
    self.assertEqual(rental.property_type, 'Apartment')
    self.assertEqual(rental.room_type, 'Entire home/apt')
    self.assertEqual(rental.nickname, '185 Newark #2')
    self.assertTrue(rental.is_active)

    self.assertEqual(
        rental.main_checkin_instructions_link,
        'main checkin instructions link')
    self.assertEqual(
        rental.main_property_access_codes_in_order_of_use,
        'main property access codes in order of use')
    self.assertEqual(
        rental.master_access_code_building_door_electronic_lock,
        'master access code building door electronic lock')
    self.assertEqual(
        rental.master_access_code_apartment_door_electronic_lock,
        'master access code apartment door electronic lock')
    self.assertEqual(
        rental.wifi_network_name,
        'wifi network name')
    self.assertEqual(
        rental.wifi_password,
        'wifi password')
    self.assertEqual(
        rental.building_trash_instructions,
        'building trash instructions')
    self.assertEqual(
        rental.link_to_property_page_in_helpdocs,
        'link to property page in helpdocs')
    self.assertEqual(
        rental.google_maps_link,
        'google maps link')
    self.assertEqual(
        rental.departure_check_list,
        'departure check list')
    self.assertEqual(
        rental.local_bag_storage_info,
        'local bag storage info')
    self.assertEqual(
        rental.local_bag_storage_link,
        'local bag storage link')
    self.assertEqual(
        rental.parking_link,
        'parking link')
    self.assertEqual(
        rental.public_transportation_link,
        'public transportation link')
    self.assertEqual(
        rental.local_recommendations_link,
        'local recommendations link')
    self.assertEqual(
        rental.walking_to_nearest_path_stations,
        'walking to nearest path stations')
    self.assertEqual(
        rental.parking_suggestions_no_links,
        'parking suggestions no links')
    self.assertEqual(
        rental.public_transport_no_link,
        'public transport no link')
    self.assertEqual(
        rental.walk_time_to_nearest_train,
        'walk time to nearest train')
    self.assertEqual(
        rental.laundry_info,
        'laundry info')


class ReservationTests(TestCase):
  def test_before_policy_security_deposit(self):
    in_effect = make_aware(parse_datetime(settings.MESSAGING_GOES_LIVE))

    # hah, in_effect - timedelta(hours=1) needs to be a string like
    # '2018-04-23T21:16:35.273Z'
    r_long_before = copy.deepcopy(RESERVATION)
    r_long_before['createdAt'] = (in_effect - timedelta(hours=1)).isoformat()
    r_long_before['money']['payments'] = []
    r_long_after = copy.deepcopy(RESERVATION)
    r_long_after['createdAt'] = (in_effect + timedelta(hours=1)).isoformat()
    r_long_after['money']['payments'] = []

    mock_getter = MockGuestyAPIGetter()
    sync = GuestySync(mock_getter)

    self.assertTrue(
        sync.sync_reservation(r_long_before).has_security_deposit())
    self.assertFalse(
        sync.sync_reservation(r_long_after).has_security_deposit())

  def test_handle_custom_push_fields(self):
    r = get_test_reservation(
        True, security_deposit=Money(300, 'USD'), is_paid_in=True)
    # Note, confusing, this isn't a MockGuestyAPIGetter.
    mock_getter = Mock(spec=GuestyAPIGetter)
    sync = GuestySync(mock_getter)
    custom_fields = CustomFields(Reservation, 'guesty_id_asdf', [])
    sync._handle_custom_fields(r, custom_fields)
    cc_auth_field_id = settings.CREDIT_CARD_AUTHORIZATION_VALID_FIELD_ID
    expected_custom_fields = [
        {'fieldId': settings.PAID_IN_FULL_FIELD_ID, 'value': True},
        {'fieldId': cc_auth_field_id, 'value': True}]
    self.assertEqual(
        [call(
            'reservations/guesty_id_asdf',
            {'customFields': expected_custom_fields})],
        mock_getter.put.call_args_list)

  def test_handle_custom_fields_for_phone(self):
    r = get_test_reservation(True, phone='111-111-1111')
    sync = GuestySync()
    sync._handle_custom_fields(r, CustomFields(
        Reservation, 'guesty_id_whatever', [{
            'fieldId': settings.PHONE_PROVIDED_FIELD_ID,
            'value': '222-222-2222'}]))
    guest = Guest.objects.get(pk=r.guest.pk)
    self.assertEqual('222-222-2222', guest.phone)
    self.assertTrue(r.guest.has_phone('111-111-1111'))
    self.assertTrue(r.guest.has_phone('222-222-2222'))

  def test_handle_custom_fields_for_id_verified(self):
    r = get_test_reservation(True, id_verified=False)
    self.assertFalse(r.id_verified)
    sync = GuestySync()
    custom_fields = CustomFields(Reservation, 'guesty_id_whatever', [{
        'fieldId': settings.ID_VERIFIED_FIELD_ID, 'value': True}])
    sync._handle_custom_fields(r, custom_fields)
    self.assertTrue(Reservation.objects.get(pk=r.pk).id_verified)
    sync._handle_custom_fields(r, CustomFields(
        Reservation, 'guesty_id_whatever', []))
    self.assertFalse(Reservation.objects.get(pk=r.pk).id_verified)

  def test_handle_custom_fields_for_messages(self):
    reservation = get_test_reservation(True)
    template = get_test_smstemplate(
        True, guesty_custom_field_id='5afa2c379ebb42009e34f270')
    template.create_new_message(reservation)
    message = SMS.objects.get_for_reservation(reservation)[0]
    self.assertTrue(message.green_light)

    sync = GuestySync()
    custom_fields = CustomFields(Reservation, '5afa2c379ebb42009e34f270', [
        {'fieldId': 'unrelated_field_id', 'value': False}])
    sync._handle_custom_fields(reservation, custom_fields)
    # Still on
    message = SMS.objects.get_for_reservation(reservation)[0]
    self.assertTrue(message.green_light)

    sync = GuestySync()
    custom_fields = CustomFields(Reservation, '5afa2c379ebb42009e34f270', [
        {'fieldId': '5afa2c379ebb42009e34f270', 'value': False}])
    sync._handle_custom_fields(reservation, custom_fields)
    message = SMS.objects.get_for_reservation(reservation)[0]
    self.assertFalse(message.green_light)

    custom_fields = CustomFields(Reservation, '5afa2c379ebb42009e34f270', [])
    sync._handle_custom_fields(reservation, custom_fields)
    message = SMS.objects.get_for_reservation(reservation)[0]
    self.assertTrue(message.green_light)

    # When an individual message is reactivated but deactivate all is
    # set, still deactivate.
    custom_fields = CustomFields(Reservation, '5afa2c379ebb42009e34f270', [
        {'fieldId': settings.ALL_AUTOMATIONS_FIELD_ID, 'value': False},
        {'fieldId': '5afa2c379ebb42009e34f270', 'value': True}])
    sync._handle_custom_fields(reservation, custom_fields)
    message = SMS.objects.get_for_reservation(reservation)[0]
    self.assertFalse(message.green_light)

  def test_handle_raw_event(self):
    """ This test is basically syncing guesty.api_examples.RESERVATION
    via a webhook. """
    raw_event = RawEvent.objects.create(
        json=json.dumps({'reservation': RESERVATION}),
        event_name='reservation.new')
    self.assertIsNone(raw_event.handled_at)
    self.assertIsNone(raw_event.reservation)

    self.assertEqual(0, Reservation.objects.filter(
        channel_reservation_id='HM123456').count())

    handled = GuestySync(MockGuestyAPIGetter()).handle_raw_event(raw_event)

    self.assertEqual(1, Reservation.objects.filter(
        channel_reservation_id='HM123456').count())
    self.assertEqual('I synced this reservation.', handled)
    raw_event.refresh_from_db()
    self.assertIsNotNone(raw_event.handled_at)
    self.assertIsNotNone(raw_event.reservation)
    self.assertEqual('HM123456', raw_event.reservation.channel_reservation_id)

  def test_alert_if_overpaid(self):
    error_logger = Mock(spec=ErrorLogger)
    no_problem = get_test_reservation(
        True, balance_due=Money(0, 'USD'))

    problem = get_test_reservation(
        True, balance_due=Money(-1, 'USD'),
        full_name='Jannet Jackson', guesty_id='blueone')

    GuestySync().alert_if_overpaid(no_problem, error_logger=error_logger)
    self.assertEqual(error_logger.log_error.call_args_list, [])

    GuestySync().alert_if_overpaid(problem, error_logger=error_logger)
    self.assertEqual(error_logger.log_error.call_args_list, [call(
        'Warning: overpaid reservation for Jannet Jackson', (
            'https://app.guesty.com/reservations/blueone/guests\n'
            'Balance due: -$1.00'), extra_to=settings.ALERT_OVERPAYMENT)])

  def test_balance_due(self):
    self.assertEqual(
        Money(0, 'USD'),
        GuestySync().get_balance_due(NO_BALANCE_DUE_MONEY))
    self.assertEqual(
        Money(0, 'USD'),
        GuestySync().get_balance_due(REFUND_NO_BALANCE_DUE_MONEY))

  def test_alert_if_overlap(self):
    rental = get_test_rental(True)
    res1 = get_test_reservation(
        True,
        rental=rental,
        check_in=now(),
        check_out=now() + timedelta(days=5),
        guesty_id='onetwothree')
    get_test_reservation(
        True,
        rental=rental,
        check_in=now() + timedelta(days=1),
        check_out=now() + timedelta(days=2),
        guesty_id='fourfive')
    error_logger = Mock(spec=ErrorLogger)
    GuestySync().alert_if_overlap(res1, error_logger=error_logger)
    message = (
        'https://app.guesty.com/reservations/onetwothree/guests\n'
        'https://app.guesty.com/reservations/fourfive/guests')
    self.assertEqual(
        error_logger.log_error.call_args_list,
        [call(
            'Warning: overlapping reservations detected!!!',
            message, always_new_error=True,
            extra_to=settings.ALERT_OVERLAPPING_RESERVATIONS)])

  def test_sync_reservation(self):
    """ This test is basically syncing guesty.api_examples.RESERVATION """
    mock_getter = MockGuestyAPIGetter()
    # We gotta put the check_out in the future because we don't bother
    # to create messages for reservations that happened already, and in
    # this test we check that a message got created.
    check_in = afternoon_from_date(now() - timedelta(days=1))
    check_out = morning_from_date(now() + timedelta(days=1))
    mock_getter.set_check_in(check_in)
    mock_getter.set_check_out(check_out)

    self.assertEqual(0, Reservation.objects.filter(
        channel_reservation_id='HM123456').count())

    # Put this way in the future to get around a) RESERVATION has a set
    # check in time and b) we don't create messages that are already overdue.
    get_test_smstemplate(
        True,
        offset=100 * 365,
        days_or_hours=DAYS,
        before_or_after=AFTER,
        preschedule_around=CHECKIN)

    GuestySync(mock_getter).sync_all_reservations()
    GuestySync(mock_getter).sync_all_reservations()

    by_channel_id = Reservation.objects.filter(
        channel_reservation_id='HM123456')
    self.assertEqual(1, by_channel_id.count())
    by_guesty_id = GuestyReservation.objects.filter(
        guesty_id='5ade4d3314fe0e004dcde909')
    self.assertEqual(1, by_guesty_id.count())
    self.assertEqual(
        by_channel_id.first().pk, by_guesty_id.first().reservation.pk)
    reservation = by_channel_id.first()

    self.assertEqual(1, len(SMS.objects.get_for_reservation(reservation)))

    self.assertEqual(reservation.channel_reservation_id, 'HM123456')
    self.assertEqual(reservation.guest.email, 'sophia@gmail.com')
    self.assertEqual(
        reservation.anonymized_email,
        'jiaxin-ku0lh5ltfwqd0be5@guest.airbnb.com')

    self.assertEqual(reservation.check_in, check_in)
    self.assertEqual(reservation.planned_arrival, time(17))
    self.assertEqual(reservation.check_out, check_out)
    self.assertEqual(reservation.reservation_created, parse_datetime(
        '2018-05-23T21:16:35.273Z'))
    self.assertEqual(
        reservation.booked_at, parse_datetime('2018-05-24T21:16:35.272Z'))
    # Don't test price per night. That's just confusing nonsense at this
    # point. Price of WHAT?! Total income? Net income? Just the rent divided
    # by the nights? Does it include the channel fees or not? Forget it.
    self.assertEqual(reservation.night_count, 2)
    self.assertEqual(reservation.total_payin, Money(1321.14, 'BZD'))
    self.assertEqual(reservation.security_deposit, Money(300, 'BOV'))
    self.assertEqual(reservation.is_paid_in, True)
    self.assertEqual(reservation.balance_due, Money(-100, 'BZD'))
    self.assertEqual(reservation.valid_payments_exist, True)
    self.assertEqual(reservation.status, 'confirmed')
    self.assertEqual(reservation.channel, BOOKINGCOM)
    self.assertEqual(
        reservation.rental.airbnb_address_scrape,
        '144 Steuben Street Apt #402, Jersey City, NJ 07302, United States')
    self.assertEqual(reservation.rental.city, 'Jersey City')
    self.assertEqual(reservation.rental.city, 'Jersey City')
    self.assertEqual(reservation.cc_last_4, '7697')
    self.assertEqual(reservation.cc_brand, 'Visa')

    guest = reservation.guest

    self.assertEqual(guest.first_name, 'Sofia')
    self.assertEqual(guest.last_name, 'Fay')
    self.assertEqual(guest.full_name, 'Sofia Fay')
    self.assertEqual(
        guest.airbnb_says_theyre_from, 'Tortola, British Virgin Islands')
    self.assertEqual(guest.phone, '+16178177271')
    self.assertEqual(
        GuestPhoneNumber.objects.filter(guest=guest)[0].raw_string,
        '+16178177271')
    self.assertEqual(guest.channel_id, '92547277')

    self.assertEqual(
        GuestyGuest.objects.get(guesty_id='5ade4ca7a989550061844c3b').guest.pk,
        guest.pk)

    got_line_items = reservation.line_items().order_by('name')
    got = [(li.name, li.value) for li in got_line_items]
    expected = [
        ('Accommodation fare', Money(1262, 'BZD')),
        ('Cleaning fee', Money(100, 'BZD')),
        ('Host channel fee', Money(-40.86, 'BZD'))]
    self.assertEqual(expected, got)
