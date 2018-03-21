from datetime import datetime
import pytz

from django.test import TestCase
from django.utils.six import BytesIO
from djmoney.money import Money
from rest_framework.renderers import JSONRenderer
from rest_framework.parsers import JSONParser

from guests.models import Guest
from guests.tests import get_test_guest
from listings.models import Listing
from listings.tests import get_test_listing
from reservations.models import Reservation, ReservationLineItem
from reservations.serializers import ReservationSerializer


def get_test_reservation(create, **kwargs):
  guest = get_test_guest(create)
  listing = get_test_listing(create)
  reservation = Reservation(
      channel_reservation_id=kwargs.get('channel_reservation_id', '12345678'),
      guest=kwargs.get('guest', guest),
      check_in=kwargs.get('check_in', datetime(2018, 3, 1, 15)),
      check_out=kwargs.get('check_out', datetime(2018, 3, 3, 11)),
      listing=kwargs.get('listing', listing),
      price_per_night=kwargs.get('price_per_night', 125),
      night_count=kwargs.get('night_count', 2),
      total_payin=kwargs.get('total_payin', 340),
      is_paid_in=kwargs.get('is_paid_in', True))
  if create:
    reservation.save()
  return reservation


def get_postable_test_reservation():
  """ This isn't used in tests exactly, but it is useful for poking around
  with the API. It also helps document how to use the API. """
  r = get_test_reservation(False)
  r.listing = None
  r.channel_listing_id = Listing.objects.all()[0].channel_listing_id
  li_rent = ReservationLineItem(name='Rent', value=250.0)
  li_cleaning = ReservationLineItem(name='Cleaning Fees', value=100.0)
  li_service = ReservationLineItem(name='Airbnb Service Fee', value=-10.5)
  r.line_items = [li_rent, li_cleaning, li_service]
  return r


class ReservationSerializationTests(TestCase):
  def test_serializing_loaded_object(self):
    # When the API returns one that's been saved to the database,
    # it serializes it. Make sure that works.
    ReservationSerializer(get_test_reservation(True)).data

  def test_serializing_manual_object_and_saving(self):
    # We want an existing listing.
    listing = get_test_listing(False)
    listing.rental.time_zone = 'US/Hawaii'
    listing.rental.save()
    listing.rental_id = listing.rental.id
    listing.channel_listing_id = 'whydoidoittomyself'
    listing.save()

    # At this point, pretend like we're in a scraper and trying to put
    # together a reservation to send through the API.
    r = get_test_reservation(False)
    r.check_in = datetime(2018, 3, 1, 16)
    r.check_out = datetime(2018, 3, 3, 13)  # They wanted a late checkout.
    r.total_payin = 339.5
    r.listing = None
    r.channel_listing_id = 'whydoidoittomyself'
    r.channel_reservation_id = 'Iblamemeandnooneelse'
    r.guest.full_name = 'Jeberoo Joinks'
    li_rent = ReservationLineItem(name='Rent', value=250.0)
    li_cleaning = ReservationLineItem(name='Cleaning Fees', value=100.0)
    li_service = ReservationLineItem(name='Airbnb Service Fee', value=-10.5)
    r.line_items = [li_rent, li_cleaning, li_service]

    # Make sure only the listing got created so far
    self.assertEqual(
        1, len(
            Listing.objects.filter(channel_listing_id='whydoidoittomyself')))
    self.assertEqual(0, len(
        Reservation.objects.filter(
            channel_reservation_id='Iblamemeandnooneelse')))
    self.assertEqual(0, len(
        Guest.objects.filter(
            full_name='Jeberoo Joinks')))

    # Serialize, deserialize, and save twice. The second time around, cut
    # the cleaning bill in half because the apartment wasn't cleaned
    # properly.
    for i in range(2):
      if i == 1:
        li_cleaning.value = 50
        r.total_payin = 289.5
      serializer = ReservationSerializer(r)
      content = JSONRenderer().render(serializer.data)

      stream = BytesIO(content)
      data = JSONParser().parse(stream)
      deserializer = ReservationSerializer(data=data)
      self.assertTrue(deserializer.is_valid())
      deserializer.create(deserializer.validated_data)

    # Make sure we didn't make extra objects.
    self.assertEqual(
        1, len(
            Listing.objects.filter(channel_listing_id='whydoidoittomyself')))
    reservations = Reservation.objects.filter(
        channel_reservation_id='Iblamemeandnooneelse')
    self.assertEqual(1, len(reservations))
    guests = Guest.objects.filter(full_name='Jeberoo Joinks')
    self.assertEqual(1, len(guests))

    # Make sure the saved versions are equal to what we expected.
    r_loaded = reservations[0]
    self.assertEqual(r.channel_reservation_id, r_loaded.channel_reservation_id)

    self.assertEqual(r.guest.full_name, r_loaded.guest.full_name)
    self.assertEqual(
        r.guest.joined_airbnb_when, r_loaded.guest.joined_airbnb_when)
    self.assertEqual(
        r.guest.airbnb_says_theyre_from,
        r_loaded.guest.airbnb_says_theyre_from)
    self.assertEqual(r.guest.phone, r_loaded.guest.phone)

    # Timezones! I believe Airbnb shows local times, so what we want here is
    # for the reservation to save with the timezone of the rental but the
    # literal hour and day we saw on the website.
    tz = pytz.timezone('US/Hawaii')
    # check_in_with_tz = datetime.datetime(
    #     2018, 3, 1, 16, 0, tzinfo=
    #         <DstTzInfo 'US/Hawaii' HST-1 day, 14:00:00 STD>)
    check_in_with_tz = tz.localize(datetime(2018, 3, 1, 16))
    check_out_with_tz = tz.localize(datetime(2018, 3, 3, 13))
    self.assertEqual(check_in_with_tz, r_loaded.check_in)
    self.assertEqual(check_out_with_tz, r_loaded.check_out)
    # This check fails because Django converts all timezone aware datetimes
    # to UTC as it fetches them.
    # self.assertEqual(16, r_loaded.check_in.hour)

    self.assertEqual(
        listing.channel_listing_id, r_loaded.listing.channel_listing_id)
    expected = Money(r.price_per_night.amount, 'USD')
    self.assertEqual(expected, r_loaded.price_per_night)
    self.assertEqual(r.night_count, r_loaded.night_count)
    self.assertEqual(Money(289.5, 'USD'), r_loaded.total_payin)
    self.assertEqual(r.is_paid_in, r_loaded.is_paid_in)

    self.assertEqual(3, len(r_loaded.line_items()))
    s1 = set([
        ('Rent', Money(250.0, 'USD')),
        ('Cleaning Fees', Money(50.0, 'USD')),
        ('Airbnb Service Fee', Money(-10.5, 'USD'))])
    s2 = set((li.name, li.value) for li in r_loaded.line_items())
    self.assertEqual(s1, s2)
