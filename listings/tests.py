from django.test import TestCase
from django.utils.six import BytesIO
from rest_framework.renderers import JSONRenderer
from rest_framework.parsers import JSONParser

from listings.models import Listing, Airvatar
from listings.serializers import ListingSerializer
from rentals.models import Rental
from rentals.tests import get_test_rental


def get_test_airvatar(**kwargs):
  # Airvatars should definitely be in place already, so by default let's
  # return saved ones.
  name = kwargs.get('name', 'Ron Burgundy')
  airvatars = Airvatar.objects.filter(name=name)
  if len(airvatars):
    return airvatars[0]
  airvatar = Airvatar(
      name=kwargs.get('name', name),
      ip=kwargs.get('ip', '127.0.0.1'),
      port=kwargs.get('port', '123456'),
      gmail_address=kwargs.get('gmail_address', 'ron_burgundy@gmail.com'),
      gmail_password=kwargs.get('gmail_password', 'thatescalatedquickly'),
      airbnb_password=kwargs.get('airbnb_password', 'imnotevenmad'))
  airvatar.save()
  return airvatar


def get_test_listing(create, **kwargs):
  listing = Listing(
      channel=kwargs.get('channel', 'Airbnb'),
      channel_listing_id=kwargs.get('channel_listing_id', '96sbdk12988'),
      airvatar=kwargs.get('airvatar', get_test_airvatar()),
      title=kwargs.get('title', 'AMAZING!!! *** By the TRAAAAAIN!!! ***'),
      rental=kwargs.get('rental', get_test_rental(create)))
  if create:
    listing.save()
  return listing


class ListingSerializationTests(TestCase):
  def test_serializing_loaded_object(self):
    # When the API returns one that's been saved to the database,
    # it serializes it. Make sure that works.
    ListingSerializer(get_test_listing(True)).data

  def test_serializing_manual_object_and_saving(self):
    # Pretend we're in a scraper and want to put together a listing
    # to save.
    get_test_airvatar(name='G.I. Jane')
    lst = get_test_listing(False, airvatar=None)
    lst.airvatar = None
    lst.airvatar_name = 'G.I. Jane'
    lst.channel_listing_id = 'disregardmymentalhealth'
    lst.title = 'AMAAAAAZING!!!1!'
    lst.rental.airbnb_address_scrape = '7 Bob st, USA'

    # Make sure neither the listing nor the rental exist yet.
    self.assertEqual(0, len(
        Listing.objects.filter(channel_listing_id='disregardmymentalhealth')))
    self.assertEqual(0, len(
        Rental.objects.filter(airbnb_address_scrape='7 Bob st, USA')))

    # Serialize, deserialize, and save twice. The second time around, change
    # the title and the time zone of the rental.
    for i in range(2):
      if i == 1:
        lst.title = 'MOOOOOre amazing!'
        Rental.objects.filter(airbnb_address_scrape='7 Bob st, USA').update(
            time_zone='US/Pacific')
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
    self.assertEqual('G.I. Jane', loaded_l.airvatar.name)
    self.assertEqual(lst.title, loaded_l.title)

    self.assertEqual(
        lst.rental.airbnb_address_scrape, loaded_rental.airbnb_address_scrape)
    self.assertEqual('US/Pacific', loaded_rental.time_zone)
    self.assertEqual(lst.rental.currency, loaded_rental.currency)
    self.assertEqual(lst.rental.accommodates, loaded_rental.accommodates)
    self.assertEqual(lst.rental.bathrooms, loaded_rental.bathrooms)
    self.assertEqual(lst.rental.bedrooms, loaded_rental.bedrooms)
    self.assertEqual(lst.rental.property_type, loaded_rental.property_type)
    self.assertEqual(lst.rental.room_type, loaded_rental.room_type)
