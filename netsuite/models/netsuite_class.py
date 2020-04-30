import re

from django.db import models
from django.db.utils import IntegrityError

from rentals.models import Rental, Building, City
from util.fields import OneToOneOrNoneField


class NetsuiteClass(models.Model):
  # In retrospect, the code is ideally unique across all netsuite classes,
  # meaning, this base class shouldn't be abstract.
  code = models.PositiveIntegerField(unique=True)

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    # This is used for all_possible_netsuite_classes which is structured as a
    # flattened tree.
    self.children = {}

  def pretty_type(self):
    raise NotImplementedError('pretty_type')

  def unique_name(self):
    raise NotImplementedError('unique_name')

  def unique_id(self):
    return '{}_{}'.format(
        self.pretty_type(), re.sub(r'[^\w]', '', self.unique_name()))

  def code_as_string(self):
    if self.code:
      return str(self.code)
    return ''

  class Meta:
    abstract = True


class StateClass(NetsuiteClass):
  state = models.CharField(max_length=200, unique=True)

  def pretty_type(self):
    return 'state'

  def unique_name(self):
    return self.state


class CityClass(NetsuiteClass):
  city = OneToOneOrNoneField(
      City, on_delete=models.CASCADE, related_name='netsuite_class')
  # The same city name can exist in multiple states. This isn't a foreign key
  # to StateClass in case somebody wants to create the code for a city before
  # they create the code for a state. This state field is necessary only
  # because the state field in class City isn't up and running yet.
  state = models.CharField(max_length=200)

  def pretty_type(self):
    return 'city'

  def unique_name(self):
    return '{}, {}'.format(self.city.name, self.state)

  class Meta:
    unique_together = ('city', 'state')


class BuildingClass(NetsuiteClass):
  building = OneToOneOrNoneField(
      Building, on_delete=models.CASCADE, related_name='netsuite_class')

  def pretty_type(self):
    return 'building'

  def unique_name(self):
    return self.building.nickname


class RentalClass(NetsuiteClass):
  """ Class here is a Netsuite specific term that's basically a code. """
  rental = OneToOneOrNoneField(
      Rental, on_delete=models.CASCADE, related_name='netsuite_class')

  def pretty_type(self):
    return 'rental'

  def unique_name(self):
    return self.rental.nickname


def all_possible_netsuite_classes():

  def existing_lookup(all_of):
    existing = {}
    for instance in all_of:
      existing[instance.unique_name()] = instance
    return existing

  states = existing_lookup(StateClass.objects.all())
  existing_cities = existing_lookup(CityClass.objects.all())
  existing_buildings = existing_lookup(
      BuildingClass.objects.all().select_related('building', 'building__city'))
  existing_rentals = existing_lookup(
      RentalClass.objects.all().select_related(
          'rental', 'rental__building', 'rental__building__city'))

  for rental in Rental.objects.filter(is_active=True).select_related(
      'building', 'building__city'):
    state_name = rental.building.city.state
    if state_name not in states:
      states[state_name] = StateClass(state=state_name)
    state_class = states[state_name]

    city_name = rental.building.city.name
    city_key = '{}, {}'.format(city_name, rental.building.city.state)
    if city_key not in state_class.children:
      state_class.children[city_key] = existing_cities.get(
          city_key, CityClass(city=rental.building.city, state=state_name))
    city_class = state_class.children[city_key]

    building_name = rental.building.nickname
    if building_name not in city_class.children:
      city_class.children[building_name] = existing_buildings.get(
          building_name, BuildingClass(building=rental.building))
    building_class = city_class.children[building_name]

    rental_name = rental.nickname
    if rental_name not in building_class.children:
      building_class.children[rental_name] = existing_rentals.get(
          rental_name, RentalClass(rental=rental))

  def recursive_return(lookup):
    for value in sorted(lookup.values(), key=lambda x: x.unique_name()):
      yield value
      for descendent in recursive_return(value.children):
        yield descendent

  for descendent in recursive_return(states):
    yield descendent


def handle_netsuite_classes_post(request_post):
  problems = []
  for netsuite_class in all_possible_netsuite_classes():
    key = netsuite_class.unique_id()
    if key in request_post:
      value = request_post[key]
      try:
        netsuite_class.code = int(value)
        netsuite_class.save()
      except ValueError:
        if value:
          problems.append((
              'You entered {}, which is not a valid code. I '
              'ignored it.').format(value))
      except IntegrityError:
        problems.append(
            'You entered a duplicate {}, which I ignored.'.format(value))
  return problems


ALL_UNITS_CLASS = 716
