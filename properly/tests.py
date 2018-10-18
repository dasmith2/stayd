from datetime import timedelta

from django.utils.timezone import now
from djmoney.money import Money

from properly.models import Cleaner, Cleaning
from rentals.tests import get_test_rental, get_test_building
from reservations.tests import get_test_reservation
from util.tests import TestCase


def get_test_cleaner(create, **kwargs):
  cleaner = Cleaner(
      name=kwargs.get('name', 'Mr Clean'),
      phone=kwargs.get('phone', '555-555-5555'),
      email=kwargs.get('email', 'mr_clean@email.email'),
      hourly_rate=kwargs.get('hourly_rate', Money('15.0', 'USD')))
  if create:
    cleaner.save()
    for building in kwargs.get('buildings', []):
      cleaner.buildings.add(building)
  elif kwargs.get('buildings'):
    raise Exception('You have to save before you can add to a many to many')
  return cleaner


def get_test_cleaning(create, **kwargs):
  reservation = get_test_reservation(True, **kwargs)
  cleaning = Cleaning(
      accepted_by=kwargs.get('accepted_by', None),
      reservation=kwargs.get('reservation', reservation),
      job_request_id=kwargs.get('job_request_id', None),
      creation_confirmed=kwargs.get('creation_confirmed', None),
      started_at=kwargs.get('started_at', None),
      completed_at=kwargs.get('completed_at', None))
  if create:
    cleaning.save()
    for cleaner in kwargs.get('offered_to', []):
      cleaning.offered_to.add(cleaner)
  elif kwargs.get('offered_to'):
    raise Exception('You have to save before you can add to a many to many')
  return cleaning


class ProperlyTests(TestCase):
  def test_available_cleaners(self):
    building = get_test_building(True)
    unrelated_building = get_test_building(True)
    res1 = get_test_reservation(
        True, check_in='2018-05-01 16:00', check_out='2018-05-02 11:00',
        rental=get_test_rental(True, building=building))
    res2 = get_test_reservation(
        True, check_in='2018-05-01 16:00', check_out='2018-05-02 11:00',
        rental=get_test_rental(True, building=building))
    mr_clean = get_test_cleaner(True, buildings=[building])
    ms_clean = get_test_cleaner(
        True, buildings=[building, unrelated_building], name='Ms Clean')
    get_test_cleaner(True)  # unrelated_cleaner
    get_test_cleaning(True, reservation=res1, accepted_by=mr_clean)

    self.assertEqual(
        [ms_clean], list(Cleaning.objects.available_cleaners(res2)))

  def test_require_cleanings(self):
    yes_1 = get_test_reservation(
        True, check_in=now() + timedelta(hours=1))
    yes_2 = get_test_reservation(
        True, check_in=now() + timedelta(days=6))
    has_a_cleaning_already = get_test_reservation(
        True, check_in=now() + timedelta(days=6))
    get_test_cleaning(True, reservation=has_a_cleaning_already)
    get_test_reservation(
        True, check_in=now() + timedelta(days=8))  # Too distant
    self.assertEqual(
        [yes_1, yes_2], list(Cleaning.objects.require_cleanings()))
