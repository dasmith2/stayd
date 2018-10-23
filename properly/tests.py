from datetime import timedelta
from dateutil.parser import parse
from unittest.mock import Mock, call

from django.utils.timezone import now
from djmoney.money import Money

from properly.api import API
from properly.api_examples import (
    ERROR_RESPONSE, CREATE_JOB, SET_SOURCE_PROPERTY_ID_RESPONSE)
from properly.models import Cleaner, Cleaning, RentalChecklist, Checklist
from rentals.tests import get_test_rental, get_test_building
from reservations.tests import get_test_reservation
from util.tests import TestCase, FakeResponse


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


def get_test_checklist(create, **kwargs):
  checklist = Checklist(
      name=kwargs.get('name', 'Cleaning'),
      properly_id=kwargs.get('properly_id', 'boopbeepboop'))
  if create:
    checklist.save()
  return checklist


def get_test_rental_checklist(create, **kwargs):
  rental = get_test_rental(create, **kwargs)
  checklist = get_test_checklist(create, **kwargs)
  rental_checklist = RentalChecklist(
      rental=kwargs.get('rental', rental),
      properly_rental_id=kwargs.get('properly_rental_id', 'blarginblorg'),
      checklist=kwargs.get('checklist', checklist),
      cleaning_duration=kwargs.get('cleaning_duration', 3),
      source_property_id=kwargs.get('source_property_id', None))
  if create:
    rental_checklist.save()
  return rental_checklist


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
        True, check_out=now() + timedelta(hours=1))
    yes_2 = get_test_reservation(
        True, check_out=now() + timedelta(days=6))
    has_a_cleaning_already = get_test_reservation(
        True, check_out=now() + timedelta(days=6))
    get_test_cleaning(True, reservation=has_a_cleaning_already)
    get_test_reservation(
        True, check_out=now() + timedelta(days=8))  # Too distant
    self.assertEqual(
        [yes_1, yes_2], list(Cleaning.objects.require_cleanings()))

  def test_create_job_requests(self):
    building = get_test_building(True)
    get_test_cleaner(
        True, buildings=[building], email='mr_clean@clean.email')
    checklist = get_test_checklist(True, properly_id='properly_checklist')
    rental = get_test_rental(True, building=building)
    get_test_rental_checklist(
        True, checklist=checklist, rental=rental, cleaning_duration=7,
        source_property_id='daves_source_id')
    get_test_reservation(
        True, check_out=parse('2018-10-28T15:00:00.000Z'),
        channel_reservation_id='ibelieveinafingcalledlove',
        rental=rental)
    api = Mock(spec=API)
    api.job_request_create.return_value = FakeResponse(True, CREATE_JOB)

    cleanings = Cleaning.objects.create_job_requests(api=api)

    self.assertEqual(1, len(cleanings))
    cleaning = cleanings[0]
    self.assertTrue(bool(cleaning.creation_confirmed))
    self.assertEqual(cleaning.job_request_id, '5bce266701ff159cd2e21656')

    expected = {
        'sourceBookingId': 'ibelieveinafingcalledlove',
        'receiveUpdates': True,
        'time': {
            'type': 'fixed',
            'startTime': '2018-10-28T15:15:00Z',
            'durationInHours': 7},
        'property': {'sourcePropertyId': 'daves_source_id'},
        'checklists': [{'checklistId': 'properly_checklist'}],
        'serviceProviders': [{'email': 'mr_clean@clean.email'}]}
    self.assertEqual([call(expected)], api.job_request_create.call_args_list)


class APITests(TestCase):
  def test_response_is_ok(self):
    api = API()
    self.assertFalse(api.response_data_is_ok(ERROR_RESPONSE))
    self.assertTrue(api.response_data_is_ok(CREATE_JOB))
    self.assertTrue(api.response_data_is_ok(SET_SOURCE_PROPERTY_ID_RESPONSE))


class RentalChecklistTests(TestCase):
  def test_set_source_property_id(self):
    rc = get_test_rental_checklist(
        True, properly_rental_id='goatsandboats', source_property_id=None)
    api = Mock(spec=API)
    api.property_update.return_value = SET_SOURCE_PROPERTY_ID_RESPONSE
    self.assertEqual('goatsandboats', rc.get_source_property_id(api=api))
    rc.refresh_from_db()
    self.assertEqual(rc.source_property_id, 'goatsandboats')
    expected = {
        'propertyId': 'goatsandboats',
        'changes': {'sourceId': 'goatsandboats'}}
    self.assertEqual([call(expected)], api.property_update.call_args_list)
