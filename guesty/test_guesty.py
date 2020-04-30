import copy
from datetime import time, timedelta
from decimal import Decimal
import json
import pprint
from unittest.mock import Mock, call

from django.conf import settings
from util.tests import TestCase
from django.utils.dateparse import parse_datetime
from django.utils.timezone import make_aware, now
from djmoney.money import Money

from errors.models import ErrorLogger, Notifier
from guest_messages.models.message import DAYS, AFTER, CHECKIN
from guest_messages.tests import get_test_smstemplate, SMS
from guests.models import Guest, GuestPhoneNumber
from guesty.guesty import Guesty
from guesty.api_examples import (
    GUEST, RENTAL, RESERVATION, RESERVATION_FOR_LIST, NO_BALANCE_DUE_MONEY,
    REFUND_NO_BALANCE_DUE_MONEY, CANCELED, SCHEDULED_PAYMENTS)
from guesty.custom_field_ids import (
    ENTER_1_TO_ACTIVATE_LISTING_IN_KEYS, TRUST_ME_CC_AUTHORIZED,
    CANARY_IN_THE_COALMINE_FIELD_ID)
from guesty.models import (
    GuestyReservation, GuestyRental, GuestyGuest, RawEvent,
    ReservedReservation)
from rentals.models import Building, Rental
from rentals.tests import get_test_rental
from reservations.models import Reservation
from reservations.tests.tests import get_test_reservation
from util.channels import BOOKINGCOM
from util.timezone import morning_from_date, afternoon_from_date


class MockGuestyAPI(object):
  """ I should replace this with Mock(spec=GuestyAPI) because that will fail
  properly if the function names change, and it will reduce custom stuff in our
  tests. """
  def __init__(self):
    self.address = None
    self.guesty_rental_id = None
    self.check_out = None
    self.check_in = None
    self.was_put = []
    self.reservation = RESERVATION
    self.reservation_for_list = RESERVATION_FOR_LIST
    self.rental_data = RENTAL

  def set_reservation(self, reservation):
    self.reservation = reservation
    self.reservation_for_list = reservation

  def set_rental_data(self, rental_data):
    self.rental_data = rental_data

  def get_one(self, type_of_thing, guesty_id, allowed_in_runserver=False):
    if type_of_thing is Guest:
      to_return = GUEST
    elif type_of_thing is Reservation:
      to_return = self.reservation
      if self.check_out:
        to_return['checkOut'] = self.check_out.isoformat()
      if self.check_in:
        to_return['checkIn'] = self.check_in.isoformat()
    elif type_of_thing is Rental:
      to_return = self.rental_data
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
      if self.address or self.guesty_rental_id:
        raise Exception(
            'Use set_rental_data now instead of setting the address and the '
            'guesty_rental_id')
        # rental_long['address']['full'], rental_long['_id']
      return [self.rental_data]
    elif type_of_thing is Reservation:
      return [self.reservation_for_list]
    raise Exception('Not sure what to do with a {}'.format(type_of_thing))

  def set_check_in(self, check_in):
    self.check_in = check_in

  def set_check_out(self, check_out):
    self.check_out = check_out

  def put(self, *args):
    self.was_put.append(args)


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
    api = WebhookAPIGetter()
    Guesty(api).sync_webhooks(
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
    equal = len(expected) == len(api.webhooks) and all(
        e in api.webhooks for e in expected)
    if not equal:
      pper = pprint.PrettyPrinter()
      print('The Webhooks test is about to fail. Expected:')
      pper.pprint(expected)
      print('Got:')
      pper.pprint(api.webhooks)
    self.assertTrue(equal)


class RentalGuestyDontSyncNicknameTests(TestCase):
  def test_too_early_to_sync_rental(self):
    self.api = MockGuestyAPI()
    rental_1 = copy.deepcopy(RENTAL)
    rental_1['_id'] = 'id1here'
    rental_1['nickname'] = 'Modern 2 BR/2 BA with Gym and Pool by Howard'
    self.api.set_rental_data(rental_1)
    Guesty(self.api).sync_rentals()

    self.assertFalse(GuestyRental.objects.exists())
    self.assertFalse(Rental.objects.exists())


class RentalGuestyIdOrNicknameChangesTests(TestCase):
  def setUp(self):
    super().setUp()
    self.api = MockGuestyAPI()
    rental_1 = copy.deepcopy(RENTAL)
    rental_1['_id'] = 'id1here'
    rental_1['nickname'] = 'nickname_1'
    self.api.set_rental_data(rental_1)
    Guesty(self.api).sync_rentals()
    self.guesty_rental = GuestyRental.objects.get(guesty_id='id1here')
    self.assertEqual('nickname_1', self.guesty_rental.rental.nickname)

    self.assertEqual(1, GuestyRental.objects.count())
    self.rental = Rental.objects.first()

  def test_sync_dif_ids_and_nicknames_notifies(self):
    get_test_rental(guesty_id='id2here', nickname='nickname_2')
    rental_3 = copy.deepcopy(RENTAL)
    rental_3['_id'] = 'id1here'
    rental_3['nickname'] = 'nickname_2'
    notifier = Mock(spec=Notifier)

    rental_3 = Guesty().sync_rental(rental_3, notifier=notifier)

    url = (
        'https://keys.hihoward.com/clean_up_dupe_rentals/?pks={},{}'.format(
            rental_3.pk, self.rental.pk))
    expected_call = call(
        ['tom@hihoward.com', 'dave@hihoward.com'],
        'One of these rentals probably needs to go away.', (
            'You can pick which is the correct one here: {}').format(url))
    self.assertEqual([expected_call], notifier.notify.call_args_list)

  def test_sync_rental_same_nickname_updates_guesty_id(self):
    """ OK, apparently as part of onboarding units, they do a, like, v1 with
    the appropriate nickname and the first guesty id. Then they deactivate that
    listing and do the real listing with the same nickname, but a different
    guesty id. So, simply update the guesty id of the old listing. """
    rental_2 = copy.deepcopy(RENTAL)
    rental_2['_id'] = 'id2here'
    rental_2['nickname'] = 'nickname_1'
    self.api.set_rental_data(rental_2)
    Guesty(self.api).sync_rentals()

    self.guesty_rental.refresh_from_db()
    self.assertEqual('id2here', self.guesty_rental.guesty_id)

    self.assertEqual(1, GuestyRental.objects.count())

  def test_sync_rental_same_id_updates_nickname(self):
    """ But also I'm pretty sure the nickname can change too. """
    rental_2 = copy.deepcopy(RENTAL)
    rental_2['_id'] = 'id1here'
    rental_2['nickname'] = 'nickname_2'
    self.api.set_rental_data(rental_2)
    Guesty(self.api).sync_rentals()

    self.guesty_rental.refresh_from_db()
    self.assertEqual('nickname_2', self.guesty_rental.rental.nickname)

    self.assertEqual(1, GuestyRental.objects.count())


class RentalTests(TestCase):
  def test_sync_only_if_activate_1(self):
    """ Only suck in rental data if the, quote, 'Enter "1" to activate this
    listing in Keys' custom field is set to 1. """
    self.api = MockGuestyAPI()
    rental_data = copy.deepcopy(RENTAL)
    for custom_field in rental_data['customFields']:
      if custom_field['fieldId'] == (
          ENTER_1_TO_ACTIVATE_LISTING_IN_KEYS):
        custom_field['value'] = None
    self.api.set_rental_data(rental_data)
    Guesty(self.api).sync_rentals()
    self.assertEqual(0, GuestyRental.objects.count())

    for custom_field in rental_data['customFields']:
      if custom_field['fieldId'] == (
          ENTER_1_TO_ACTIVATE_LISTING_IN_KEYS):
        custom_field['value'] = 1
    self.api.set_rental_data(rental_data)
    Guesty(self.api).sync_rentals()
    self.assertEqual(1, GuestyRental.objects.count())

  def test_sync_rentals_buildings(self):
    self.assertEqual(0, Building.objects.count())

    unit_1 = copy.deepcopy(RENTAL)
    unit_1['_id'] = 'Unit1guestyID'
    unit_1['nickname'] = 'nickname 1 here'
    unit_1['address']['apt'] = '1'
    unit_1['address']['full'] = (
        '144 Steuben Street Apt #1, Jersey City, NJ 07300, '
        'United States')

    unit_2 = copy.deepcopy(RENTAL)
    unit_2['_id'] = 'Unit2guestyID'
    unit_2['nickname'] = 'nickname 2!'
    unit_2['address']['apt'] = '2'
    unit_2['address']['full'] = (
        '144 Steuben Street Apt #2, Jersey City, NJ 07300, '
        'United States')

    unit_3 = copy.deepcopy(RENTAL)
    unit_3['_id'] = 'Unit3guestyID'
    unit_3['nickname'] = 'nickname 3 kids'
    unit_3['address'] = {
        'apt': 'Apt 1',
        'city': 'Madison',
        'country': 'United States',
        'full': (
            '609 S. Baldwin St. Apt 1, Madison, WI 07302, '
            'United States'),
        'state': 'WI',
        'street': '609 S. Baldwin St.',
        'zipcode': '53703'}

    guesty = Guesty()
    rental1 = guesty.sync_rental(unit_1)
    rental2 = guesty.sync_rental(unit_2)
    rental3 = guesty.sync_rental(unit_3)

    self.assertEqual(2, Building.objects.count())
    self.assertNotEqual(rental1, rental2)
    self.assertEqual(rental1.building, rental2.building)
    self.assertNotEqual(rental1.building, rental3.building)

  def test_sync_rentals(self):
    # This basically tests syncing RENTAL
    api = MockGuestyAPI()
    rental_data = copy.deepcopy(RENTAL)
    rental_data['address']['full'] = '221b Baker St., London, UK'
    rental_data['_id'] = '5e5e5e'
    api.set_rental_data(rental_data)

    self.assertEqual(0, Rental.objects.filter(
        full_address='221b Baker St., London, UK').count())
    self.assertEqual(0, Building.objects.count())

    Guesty(api).sync_rentals()
    Guesty(api).sync_rentals()

    self.assertEqual(1, Rental.objects.filter(
        full_address='221b Baker St., London, UK').count())
    self.assertEqual(1, Building.objects.count())

    rental = GuestyRental.objects.filter(guesty_id='5e5e5e').first().rental
    building = rental.building

    self.assertEqual('Jersey City', building.city.name)
    self.assertEqual('NJ', building.city.state)
    self.assertEqual('United States', building.city.country)
    self.assertEqual('144 Steuben Street', building.street)
    self.assertEqual('07302', building.zipcode)
    self.assertEqual('America/New_York', building.time_zone)
    self.assertEqual(None, building.owner)
    self.assertEqual('144 Steuben Street, NJ', building.nickname)
    self.assertEqual(True, building.is_active)
    self.assertEqual(Decimal('40.719452'), building.latitude)
    self.assertEqual(Decimal('-74.039574'), building.longitude)

    self.assertEqual(
        rental.full_address, '221b Baker St., London, UK')
    self.assertEqual(rental.street, '144 Steuben Street')
    self.assertEqual(rental.apartment, 'Apt #402')
    self.assertEqual(rental.building.time_zone, 'America/New_York')
    self.assertEqual(rental.building.currency, 'USD')
    self.assertEqual(rental.accommodates, 10)
    self.assertEqual(rental.bathrooms, 2)
    self.assertEqual(rental.bedrooms, 3)
    self.assertEqual(rental.property_type, 'Apartment')
    self.assertEqual(rental.room_type, 'Entire home/apt')
    self.assertEqual(rental.nickname, '185 Newark #2')
    self.assertTrue(rental.is_active)
    self.assertEqual(rental.cleaning_fee, Money('100', 'USD'))
    self.assertEqual(rental.extra_guest_fee, Money('25', 'USD'))
    self.assertEqual(rental.guests_before_fee, 6)

    self.assertEqual(2, rental.amenities.count())
    rental.amenities.get(name='TV')
    rental.amenities.get(name='Wide entryway')

    self.assertEqual(5, rental.bed_count)
    self.assertEqual(
        'Create a memorable vacation or business trip.',
        rental.brief_description)
    self.assertEqual(2, rental.rentalphoto_set.count())
    root = '//guestybookings.s3.amazonaws.com/listings/'
    rental.rentalphoto_set.get(
        thumbnail_url=root + 'thumbnail_384429357.jpg',
        regular_url=root + 'regular_384429357.jpg',
        large_url=root + 'large_384429357.jpg',
        original_url=root + 'original_384429357.jpg')
    rental.rentalphoto_set.get(
        thumbnail_url=root + 'thumbnail_384429456.jpg',
        regular_url=root + 'regular_384429456.jpg',
        large_url=root + 'large_384429456.jpg',
        original_url=root + 'original_384429456.jpg')

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
        rental.backup_check_in_codes,
        'Backup check-in codes')
    self.assertEqual(
        rental.backup_check_in_instructions_link,
        'Backup check-in instructions link')
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
    self.assertTrue(
        rental.online_store_available)
    self.assertFalse(
        rental.is_test_rental)
    self.assertEqual(
        rental.extra_details,
        'Extra details here')
    self.assertEqual(
        rental.leave_the_keys,
        'Leave the keys up on the table')


class ReservedReservationTests(TestCase):
  def setUp(self):
    super().setUp()
    self.res_data = copy.deepcopy(RESERVATION)
    self.res_data['_id'] = 'Humblerella'
    self.res_data['confirmationCode'] = 'NursingHerToDeath'
    api = MockGuestyAPI()
    self.guesty = Guesty(api)

  def test_new_reserved_reservation_creates_poll(self):
    self.res_data['status'] = 'reserved'
    self.guesty.sync_reservation(self.res_data)
    self.assertFalse(Reservation.objects.all().exists())
    ReservedReservation.objects.get(guesty_id='Humblerella')

  def test_existing_confirmed_declined_cancels(self):
    res = get_test_reservation(guesty_id='Humblerella', status='confirmed')
    self.res_data['status'] = 'declined'
    self.guesty.sync_reservation(self.res_data)
    res.refresh_from_db()
    self.assertEqual('canceled', res.status)


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

    api = MockGuestyAPI()
    sync = Guesty(api)

    self.assertTrue(
        sync.sync_reservation(r_long_before).has_security_deposit())
    self.assertFalse(
        sync.sync_reservation(r_long_after).has_security_deposit())

  def test_trust_me_cc_authorized(self):
    r_trust_me = copy.deepcopy(RESERVATION)
    r_trust_me['createdAt'] = now().isoformat()
    r_trust_me['money']['payments'] = []
    r_trust_me['customFields'].append({
        'fieldId': TRUST_ME_CC_AUTHORIZED,
        'value': True})
    api = MockGuestyAPI()
    sync = Guesty(api)

    self.assertTrue(
        sync.sync_reservation(r_trust_me).has_security_deposit())

  def test_handle_raw_event(self):
    """ This test is basically syncing guesty.api_examples.RESERVATION
    via a webhook. """
    raw_event = RawEvent.objects.create(
        json=json.dumps({'reservation': RESERVATION}),
        event_name='reservation.new')
    self.assertIsNone(raw_event.handled_at)
    self.assertIsNone(raw_event.reservation)

    self.assertEqual(0, Reservation.objects.filter(
        channel_id='HM123456').count())

    handled = Guesty(MockGuestyAPI()).handle_raw_event(raw_event)

    self.assertEqual(1, Reservation.objects.filter(
        channel_id='HM123456').count())
    self.assertEqual('I synced this reservation.', handled)
    raw_event.refresh_from_db()
    self.assertIsNotNone(raw_event.handled_at)
    self.assertIsNotNone(raw_event.reservation)
    self.assertEqual('HM123456', raw_event.reservation.channel_id)

  def test_balance_due(self):
    self.assertEqual(
        Money(0, 'USD'),
        Guesty().get_balance_due(NO_BALANCE_DUE_MONEY))
    self.assertEqual(
        Money(0, 'USD'),
        Guesty().get_balance_due(REFUND_NO_BALANCE_DUE_MONEY))

  def test_alert_if_overlap(self):
    rental = get_test_rental()
    res1 = get_test_reservation(
        rental=rental,
        check_in=now(),
        check_out=now() + timedelta(days=5),
        guesty_id='onetwothree')
    get_test_reservation(
        rental=rental,
        check_in=now() + timedelta(days=1),
        check_out=now() + timedelta(days=2),
        guesty_id='fourfive')
    error_logger = Mock(spec=ErrorLogger)
    Guesty().alert_if_overlap(res1, error_logger=error_logger)
    message = (
        'https://app.guesty.com/reservations/onetwothree/guests\n'
        'https://app.guesty.com/reservations/fourfive/guests')
    self.assertEqual(
        error_logger.log_error.call_args_list,
        [call(
            'Warning: overlapping reservations detected!!!',
            message, extra_to=settings.ALERT_OVERLAPPING_RESERVATIONS)])

  def test_sync_reservation_new_custom_fields(self):
    """ There was a bug lurking for a long time in guesty where the custom
    fields list was included under the listing object in reservation.new
    webhooks, but under the reservation in reservation.updated webhooks. We
    only noticed it when we started pushing out a new custom field immediately
    on reservation.new. """
    raw = RawEvent.objects.create(
        json=open('guesty/customFieldsInWrongSpot.json').read(),
        event_name='reservation.new')
    api = MockGuestyAPI()
    Guesty(api).handle_raw_event(raw)
    self.assertEqual(1, len(api.was_put))
    was_put = api.was_put[0]
    (put_url, put_data) = was_put
    self.assertEqual('reservations/5be367a23d6aea0039b12186', put_url)
    self.assertTrue('customFields' in put_data)
    fields = put_data['customFields']
    all_id = CANARY_IN_THE_COALMINE_FIELD_ID
    all_automations = [fd for fd in fields if fd['fieldId'] == all_id][0]
    self.assertTrue(all_automations['value'])

  def test_sync_reservation(self):
    """ This test is basically syncing guesty.api_examples.RESERVATION """
    api = MockGuestyAPI()
    # We gotta put the check_out in the future because we don't bother
    # to create messages for reservations that happened already, and in
    # this test we check that a message got created.
    check_in = afternoon_from_date(now() - timedelta(days=1))
    check_out = morning_from_date(now() + timedelta(days=1))
    api.set_check_in(check_in)
    api.set_check_out(check_out)

    self.assertEqual(0, Reservation.objects.filter(
        channel_id='HM123456').count())

    # Put this way in the future to get around a) RESERVATION has a set
    # check in time and b) we don't create messages that are already overdue.
    get_test_smstemplate(
        offset=100 * 365,
        days_or_hours=DAYS,
        before_or_after=AFTER,
        preschedule_around=CHECKIN)

    for i in range(2):
      Guesty(api).sync_all_reservations()

    by_channel_id = Reservation.objects.filter(
        channel_id='HM123456')
    self.assertEqual(1, by_channel_id.count())
    by_guesty_id = GuestyReservation.objects.filter(
        guesty_id='5ade4d3314fe0e004dcde909')
    self.assertEqual(1, by_guesty_id.count())
    self.assertEqual(
        by_channel_id.first().pk, by_guesty_id.first().reservation.pk)
    reservation = by_channel_id.first()

    self.assertEqual(1, len(SMS.objects.get_for_reservation(reservation)))

    self.assertEqual(reservation.channel_id, 'HM123456')
    self.assertEqual(reservation.guest.email, 'sophia@gmail.com')
    self.assertEqual(
        reservation.anonymized_email,
        'jiaxin-ku0lh5ltfwqd0be5@guest.airbnb.com')

    self.assertEqual(reservation.check_in, check_in)
    self.assertEqual(reservation.planned_arrival, time(17))
    self.assertEqual(reservation.check_out, check_out)
    self.assertEqual(reservation.reservation_created, parse_datetime(
        '2018-05-23T21:16:35.273Z'))
    self.assertEqual(reservation.imported_at, parse_datetime(
        '2018-04-23T21:16:35.272Z'))
    self.assertEqual(
        reservation.booked_at, parse_datetime('2018-05-24T21:16:35.272Z'))
    self.assertEqual(reservation.ideal_payin, Money(1321.14, 'USD'))
    self.assertEqual(
        parse_datetime('2018-04-25T07:47:59.543Z'),
        reservation.first_payment_scheduled_on)
    self.assertEqual(reservation.maximum_authorization_hold, Money(300, 'BOV'))
    self.assertEqual(reservation.is_paid_in(), True)
    self.assertEqual(reservation.get_balance_due(), Money(-100, 'USD'))
    self.assertEqual(reservation.valid_payments_exist, True)
    self.assertEqual(reservation.status, 'confirmed')
    self.assertEqual(reservation.issues, 'Guest\'s card is incorrect.')
    self.assertEqual(reservation.channel, BOOKINGCOM)
    self.assertEqual(
        reservation.rental.full_address,
        '144 Steuben Street Apt #402, Jersey City, NJ 07302, United States')
    self.assertEqual(reservation.rental.building.city.name, 'Jersey City')
    self.assertEqual(reservation.cc_last_4, '7697')
    self.assertEqual(reservation.cc_brand, 'Visa')
    self.assertEqual(reservation.guest_count, 4)

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
        ('Accommodation fare', Money(1262, 'USD')),
        ('Cleaning fee', Money(100, 'USD')),
        ('Host channel fee', Money(-40.86, 'USD'))]
    self.assertEqual(expected, got)

  def test_sync_cancelled_reservation(self):
    api = MockGuestyAPI()
    api.set_reservation(CANCELED)
    Guesty(api).sync_all_reservations()

    res = GuestyReservation.objects.get(
        guesty_id='5c01a2b5fe4ac3002a2b9461').reservation
    self.assertEqual('canceled', res.status)
    self.assertEqual(
        parse_datetime('2018-12-03T04:30:46.739Z'), res.canceled_at)
    self.assertTrue(res.payment_set.count() > 0)

  def test_first_payment_scheduled_on(self):
    self.assertEqual(
        parse_datetime('2019-01-02 18:08:01.467Z'),
        Guesty().first_payment_scheduled_on(SCHEDULED_PAYMENTS))

  def test_existing_reservation(self):
    # One time, the channel_id changed and I got duplicates.
    api = MockGuestyAPI()
    guesty = Guesty(api)

    start_state = copy.deepcopy(RESERVATION)
    start_state['_id'] = 'Humblerella'
    start_state['confirmationCode'] = 'NursingHerToDeath'
    guesty.sync_reservation(start_state)
    self.assertEqual(1, Reservation.objects.count())
    res = Reservation.objects.first()
    self.assertEqual('Humblerella', res.guestyreservation.guesty_id)
    self.assertEqual('NursingHerToDeath', res.channel_id)

    channel_id_changes = copy.deepcopy(start_state)
    channel_id_changes['confirmationCode'] = 'MarketingMeritocracy'
    guesty.sync_reservation(channel_id_changes)
    self.assertEqual(1, Reservation.objects.count())
    res = Reservation.objects.first()
    self.assertEqual('Humblerella', res.guestyreservation.guesty_id)
    self.assertEqual('MarketingMeritocracy', res.channel_id)

    guesty_id_changes = copy.deepcopy(channel_id_changes)
    guesty_id_changes['_id'] = 'WhatIsWrongWithPeople'
    guesty.sync_reservation(guesty_id_changes)
    self.assertEqual(1, Reservation.objects.count())
    res = Reservation.objects.first()
    self.assertEqual('WhatIsWrongWithPeople', res.guestyreservation.guesty_id)
    self.assertEqual('MarketingMeritocracy', res.channel_id)

    both_change = copy.deepcopy(guesty_id_changes)
    both_change['_id'] = 'BusinessFinanceBusinessLoans'
    both_change['confirmationCode'] = 'IDidntKnitYouThatHat'
    guesty.sync_reservation(both_change)
    self.assertEqual(2, Reservation.objects.count())
