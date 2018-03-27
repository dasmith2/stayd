from django.test import TestCase

from rentals.models import Rental, Owner


def get_test_owner(create, **kwargs):
  owner = Owner(
      name=kwargs.get('name', 'The queen of England'),
      email=kwargs.get('email', 'thequeenofengland@gmail.com'))
  if create:
    owner.save()
  return owner


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
      room_type=kwargs.get('room_type', 'Entire home/apt'),
      owner=kwargs.get('owner', get_test_owner(create)))
  if create:
    rental.save()
  return rental
