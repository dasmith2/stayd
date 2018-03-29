from django.test import TestCase
from django.utils.dateparse import parse_datetime
from djmoney.money import Money

from guests.models import GuestPhoneNumber
from listings.tests import get_test_listing
from reservations.models import Reservation
from vreasy.models import VreasyLoader, VreasyProperty


PROPERTY_ID = 86379


class MockVreasyAPI(object):
  def get_properties(self):
    return [{
        'accommodates': 2,
        'accommodates_max': 2,
        'active': 1,
        'availability_updated_at': '2018-03-26 23:26:30',
        'checkin': '15:00:00',
        'checkout': '12:00:00',
        'cleaning_time': 4,
        'cleaning_time_min': 240,
        'created_at': '2016-09-06 14:59:15',
        'days_from_checkin_balance_due': -45,
        'deposit_percentage': 30,
        'enable_automatic_payment_at_checkin': 1,
        'has_cleaning_fee_when_booking': 1,
        'host_id': 991,
        'hours_within_deposit_due': 24,
        'id': PROPERTY_ID,
        'is_content_valid': 1,
        'rental_agreement_url': (
            'https://www.vreasy.com/rental-agreements?property=145QZV1ETT'),
        'title': 'Duplex with Private Bathroom by Times Square',
        'type_id': 2,
        'updated_at': '2018-03-19 13:47:10',
        'visible': 1}]

  def get_recently_modified_reservations(self):
    return [{
        'accommodation_cost': 141.62,
        'additional_description': 'Said between 3 and 4',
        'adults': 2,
        'checkin': '2018-03-24T15:00:00-04:00',
        'checkout': '2018-03-25T12:00:00-04:00',
        'created_at': '2017-11-06 21:04:37',
        'currency_id': 2,
        'guest': {
            'account_status': 'normal',
            'created': '2017-11-06 22:04:37',
            'email': 'john-n9fshfie7xkoz39n@guest.airbnb.com',
            'fname': 'John',
            'full_name': 'John McGonagle',
            'guest_id': 12386996,
            'lname': 'McGonagle',
            'phone': '+1 (339) 221-2095',
            'phone_international_format': '+13392212095',
            'updated': '2017-11-06 22:04:37'},
        'guest_id': 12386996,
        'host_id': 991,
        'id': 5651019,
        'kids': 0,
        'language_id': 1,
        'listor_id': 3,
        'portal_service_fee_for_pm': 4.38,
        'portal_uid': 'HMR5FCR4QT',
        'property_id': PROPERTY_ID,
        'status': 'CONFIRMED',
        'subscription_id': 32314,
        'updated_at': '2018-03-21 15:10:51',
        'user_id': 2375286}]


class PullRecentReservationsTests(TestCase):
  def test_pull_recent_reservations(self):
    listing = get_test_listing(True)
    # Get the property set up.
    loader = VreasyLoader(MockVreasyAPI())
    properties = VreasyProperty.objects.all()
    self.assertEqual(0, len(properties))
    loader.pull_properties()
    properties = VreasyProperty.objects.all()
    self.assertEqual(1, len(properties))
    properties.update(rental=listing.rental)

    start_reservation_count = Reservation.objects.all().count()

    reservation = loader.pull_recent_reservations()[0]

    self.assertEqual(
        start_reservation_count + 1, Reservation.objects.all().count())

    self.assertEqual(listing.rental.id, reservation.listing.rental.id)

    self.assertEqual('HMR5FCR4QT', reservation.channel_reservation_id)
    check_in = parse_datetime('2018-03-24T15:00:00-04:00')
    check_out = parse_datetime('2018-03-25T12:00:00-04:00')
    self.assertEqual(check_in, reservation.check_in)
    self.assertEqual(check_out, reservation.check_out)
    self.assertEqual(Money(141.62, 'USD'), reservation.total_payin)
    self.assertEqual(1, reservation.night_count)

    self.assertEqual('John McGonagle', reservation.guest.full_name)
    self.assertEqual('+1 (339) 221-2095', reservation.guest.phone)
    self.assertEqual(12386996, reservation.guest.vreasy_id)

    phone = GuestPhoneNumber.objects.get(guest=reservation.guest)
    self.assertEqual('+1 (339) 221-2095', phone.raw_string)
    self.assertEqual('13392212095', phone.numbers_only)

    loader.pull_recent_reservations()
    self.assertEqual(
        start_reservation_count + 1, Reservation.objects.all().count())
