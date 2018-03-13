from django.test import TestCase
from django.utils.six import BytesIO
from rest_framework.renderers import JSONRenderer
from rest_framework.parsers import JSONParser

from listings.models import Listing
from listings.serializers import ListingSerializer
from rentals.models import Rental
from rentals.tests import get_test_rental


def get_test_listing(create, **kwargs):
  rental = get_test_rental(create)
  listing = Listing(
      channel=kwargs.get('channel', 'Airbnb'),
      channel_listing_id=kwargs.get('channel_listing_id', '96sbdk12988'),
      firefox_profile=kwargs.get('firefox_profile', 'Abe.9skdndk9'),
      title=kwargs.get('title', 'AMAZING!!! *** By the TRAAAAAIN!!! ***'),
      rental=kwargs.get('rental', rental))
  if create:
    listing.save()
  return listing


class ListingSerializationTests(TestCase):
  def test_serializing_and_saving(self):
    # Pretend we're in a scraper and want to put together a listing
    # to save.
    lst = get_test_listing(False)
    lst.channel_listing_id = 'disregardmymentalhealth'
    lst.title = 'AMAAAAAZING!!!1!'
    lst.rental.airbnb_address_scrape = '7 Bob st, USA'

    # Make sure neither the listing nor the rental exist yet.
    self.assertEqual(0, len(
        Listing.objects.filter(channel_listing_id='disregardmymentalhealth')))
    self.assertEqual(0, len(
        Rental.objects.filter(airbnb_address_scrape='7 Bob st, USA')))

    # Serialize, deserialize, and save twice. The second time around, change
    # the title.
    for i in range(2):
      if i == 1:
        lst.title = 'MOOOOOre amazing!'
      serializer = ListingSerializer(lst)
      content = JSONRenderer().render(serializer.data)
      stream = BytesIO(content)
      data = JSONParser().parse(stream)
      deserializer = ListingSerializer(data=data)
      self.assertTrue(deserializer.is_valid())
      deserializer.create(deserializer.validated_data)

    # Make sure we didn't make extra objects.
    listings = Listing.objects.filter(
        channel_listing_id='disregardmymentalhealth')
    self.assertEqual(1, len(listings))
    rentals = Rental.objects.filter(airbnb_address_scrape='7 Bob st, USA')
    self.assertEqual(1, len(rentals))

    # Make sure the saved versions are equal to what we expected.
    loaded_l = listings[0]
    loaded_rental = rentals[0]
    self.assertEqual(lst.channel, loaded_l.channel)
    self.assertEqual(lst.channel_listing_id, loaded_l.channel_listing_id)
    self.assertEqual(lst.firefox_profile, loaded_l.firefox_profile)
    self.assertEqual(lst.title, loaded_l.title)

    self.assertEqual(
        lst.rental.airbnb_address_scrape, loaded_rental.airbnb_address_scrape)
    self.assertEqual(lst.rental.time_zone, loaded_rental.time_zone)
    self.assertEqual(lst.rental.currency, loaded_rental.currency)
    self.assertEqual(lst.rental.accommodates, loaded_rental.accommodates)
    self.assertEqual(lst.rental.bathrooms, loaded_rental.bathrooms)
    self.assertEqual(lst.rental.bedrooms, loaded_rental.bedrooms)
    self.assertEqual(lst.rental.property_type, loaded_rental.property_type)
    self.assertEqual(lst.rental.room_type, loaded_rental.room_type)
