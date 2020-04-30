from random import randint

from netsuite.models.location import Location
from rentals.tests import get_test_rental


def get_test_location(**kwargs):
  rental = kwargs.get('rental', None)
  if not rental:
    rental = get_test_rental(**kwargs)
  location_id = kwargs.get('location_id', randint(0, 1000))
  return Location.objects.create(rental=rental, location_id=location_id)
