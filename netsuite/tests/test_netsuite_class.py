from random import randint

from netsuite.models.netsuite_class import (
    all_possible_netsuite_classes, handle_netsuite_classes_post,
    StateClass, CityClass, BuildingClass, RentalClass)
from rentals.tests import get_test_rental, get_test_building, get_test_city
from util.random_string import random_string
from util.tests import TestCase


def get_test_state_class(**kwargs):
  return StateClass.objects.create(
      state=kwargs.get('state', random_string()),
      code=kwargs.get('code', randint(0, 10000)))


def get_test_city_class(**kwargs):
  city = kwargs.get('city', None)
  if not city:
    city = get_test_city(**kwargs)
  elif isinstance(city, str):
    raise Exception('City is an object, not a string')
  return CityClass.objects.create(
      city=kwargs.get('city', random_string()),
      state=kwargs.get('state', random_string()),
      code=kwargs.get('code', randint(0, 10000)))


def get_test_building_class(**kwargs):
  building = kwargs.get('building', None)
  if not building:
    building = get_test_building(**kwargs)
  return BuildingClass.objects.create(
      building=building,
      code=kwargs.get('code', randint(0, 10000)))


def get_test_rental_class(**kwargs):
  rental = kwargs.get('rental', None)
  if not rental:
    rental = get_test_rental(**kwargs)
  return RentalClass.objects.create(
      rental=rental,
      code=kwargs.get('code', randint(0, 10000)))


class NetsuiteClassesTests(TestCase):
  def setUp(self):
    super().setUp()
    la = get_test_city(name='L.A.', state='California')
    sebs = get_test_building(city=la, nickname='Sebs building')
    get_test_rental(building=sebs, nickname='Sebs #1')
    buffalo = get_test_city(name='Buffalo', state='New York')
    marias = get_test_building(
        city=buffalo, state='New York', nickname='Marias building')
    self.marias_1 = get_test_rental(building=marias, nickname='Marias #1')
    new_york = get_test_city(name='New York', state='New York')
    marcs = get_test_building(
        city=new_york, state='New York', nickname='Marcs building')
    get_test_rental(building=marcs, nickname='Marcs #1')
    daves = get_test_building(
        city=new_york, state='New York', nickname='Daves building')
    get_test_rental(building=daves, nickname='Daves #1')
    daves_2 = get_test_rental(building=daves, nickname='Daves #2')

    self.california_class = get_test_state_class(state='California', code=123)
    self.la_class = get_test_city_class(
        city=la, state='California', code=234)
    self.marias_class = get_test_building_class(building=marias, code=345)
    self.dave_2_class = get_test_rental_class(rental=daves_2, code=456)

    # Shouldn't show up because no rental has this city. Although, all states
    # show up regardless of whether there's a rental.
    get_test_city_class(
        city=get_test_city(name='Salt Lake City'), state='Utah', code=333)

  def test_all_possible_netsuite_classes(self):
    ns_classes = list(all_possible_netsuite_classes())
    i = 0
    self.assertEqual('California', ns_classes[i].unique_name())
    self.assertEqual(123, ns_classes[i].code)
    self.assertTrue(ns_classes[i].pk)
    i += 1
    self.assertEqual('L.A., California', ns_classes[i].unique_name())
    self.assertEqual(234, ns_classes[i].code)
    self.assertTrue(ns_classes[i].pk)
    i += 1
    self.assertEqual('Sebs building', ns_classes[i].unique_name())
    self.assertFalse(ns_classes[i].pk)
    i += 1
    self.assertEqual('Sebs #1', ns_classes[i].unique_name())
    self.assertFalse(ns_classes[i].pk)
    i += 1
    self.assertEqual('New York', ns_classes[i].unique_name())
    i += 1
    self.assertEqual('Buffalo, New York', ns_classes[i].unique_name())
    i += 1
    self.assertEqual('Marias building', ns_classes[i].unique_name())
    self.assertEqual(345, ns_classes[i].code)
    i += 1
    self.assertEqual('Marias #1', ns_classes[i].unique_name())
    i += 1
    self.assertEqual('New York, New York', ns_classes[i].unique_name())
    i += 1
    self.assertEqual('Daves building', ns_classes[i].unique_name())
    i += 1
    self.assertEqual('Daves #1', ns_classes[i].unique_name())
    i += 1
    self.assertEqual('Daves #2', ns_classes[i].unique_name())
    self.assertEqual(456, ns_classes[i].code)
    i += 1
    self.assertEqual('Marcs building', ns_classes[i].unique_name())
    i += 1
    self.assertEqual('Marcs #1', ns_classes[i].unique_name())

    self.assertEqual(i + 1, len(ns_classes))

  def test_handle_netsuite_classes_post(self):
    post = {
        'state_California': '321',
        'state_NewYork': '987',
        'city_LACalifornia': '432',
        'building_Mariasbuilding': '543',
        'rental_Marias1': '555',
        'rental_Daves1': 'blargh',
        'rental_Marcs1': '',
        'rental_Daves2': '654'}
    handle_netsuite_classes_post(post)

    self.california_class.refresh_from_db()
    self.assertEqual(321, self.california_class.code)
    StateClass.objects.get(state='New York', code=987)
    self.la_class.refresh_from_db()
    self.assertEqual(432, self.la_class.code)
    self.marias_class.refresh_from_db()
    self.assertEqual(543, self.marias_class.code)
    self.dave_2_class.refresh_from_db()
    self.assertEqual(654, self.dave_2_class.code)
    RentalClass.objects.get(rental=self.marias_1, code=555)
    # The codes for Daves1 and Marcs1 aren't integers.
    self.assertEqual(2, RentalClass.objects.count())
