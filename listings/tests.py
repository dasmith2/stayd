from listings.models import Listing
from rentals.tests import get_test_rental


def get_test_listing(create, **kwargs):
  listing = Listing(
      channel=kwargs.get('channel', 'Airbnb'),
      channel_listing_id=kwargs.get('channel_listing_id', '96sbdk12988'),
      title=kwargs.get('title', 'AMAZING!!! *** By the TRAAAAAIN!!! ***'),
      rental=kwargs.get('rental', get_test_rental(create)))
  if create:
    listing.save()
  return listing
