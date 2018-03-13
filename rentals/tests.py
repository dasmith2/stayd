from django.test import TestCase

from rentals.models import Host, Rental


def get_test_rental(create, **kwargs):
  rental = Rental(
      airbnb_address_scrape=kwargs.get(
          'airbnb_address_scrape', '254 Penwipper Dr., Bismund, Montana'),
      time_zone=kwargs.get('time_zone', 'US/Central'),
      currency=kwargs.get('currency', 'USD'),
      accommodates=kwargs.get('accommodates', 2),
      bathrooms=kwargs.get('bathrooms', 1),
      bedrooms=kwargs.get('bedrooms', 1),
      property_type=kwargs.get('property_type', 'Apartment'),
      room_type=kwargs.get('room_type', 'Entire home/apt'))
  if create:
    rental.save()
  return rental


class HostTests(TestCase):
  def test_save_and_load(self):
    Host.objects.create(name='Jane from L.A.')
    jane = Host.objects.get(name='Jane from L.A.')
    self.assertTrue(jane.id, 'Jane exists.')
