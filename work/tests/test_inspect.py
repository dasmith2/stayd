import json
from unittest.mock import Mock

from django.shortcuts import reverse

from work.api import API
from work.api_examples import CREATE_JOB
from work.models.inspect import (
    Inspection, NeedsInspectionScore, get_cleaner_report)
from work.models.work import CREATED, CANCELED
from work.models.work_type import CLEANER, CLEANING_INSPECTOR
from work.tests.test_cleaning import (
    get_test_cleaning, get_test_cleaning_config)
from work.tests.test_rental import get_test_properly_rental
from work.tests.test_work import set_work_stuff
from work.tests.test_worker import get_test_independent_worker
from rentals.tests import get_test_building, get_test_rental
from reservations.tests import get_test_reservation
from typeform.api_examples import CLEANING_INSPECTION_RESPONSE
from typeform.models import RawEvent
from typeform.tests import get_test_response
from util.tests import TestCase
from util.timezone import str_to_tz_dt


def get_test_inspection(**kwargs):
  inspect_cleaning = kwargs.get('inspect_cleaning', None)
  if not inspect_cleaning:
    inspect_cleaning = get_test_cleaning(**kwargs)
  inspection = Inspection(
      inspect_cleaning=inspect_cleaning,
      response=kwargs.get('response', None))
  set_work_stuff(inspection, **kwargs)
  return inspection


class NeedsInspectionScoreTests(TestCase):
  def test_assign_scores(self):
    never = get_test_independent_worker()
    just_inspected = get_test_independent_worker()
    get_test_inspection(
        offered_start_time=str_to_tz_dt('2018-09-01 15:00'),
        inspect_cleaning=get_test_cleaning(
            accepted_by=just_inspected,
            offered_start_time=str_to_tz_dt('2018-09-01 12:00'),
            completed_at=str_to_tz_dt('2018-09-01 12:00')))
    score_not_submitted = get_test_independent_worker()
    get_test_inspection(
        offered_start_time=str_to_tz_dt('2018-09-01 15:00'),
        inspect_cleaning=get_test_cleaning(
            accepted_by=score_not_submitted,
            offered_start_time=str_to_tz_dt('2018-09-01 12:00'),
            completed_at=str_to_tz_dt('2018-09-01 12:00')))
    get_test_cleaning(
        accepted_by=score_not_submitted,
        completed_at=str_to_tz_dt('2018-09-02 12:00'),
        offered_start_time=str_to_tz_dt('2018-09-02 12:00'))
    five_ago = get_test_independent_worker()
    get_test_inspection(
        response=get_test_response(score=90),
        offered_start_time=str_to_tz_dt('2018-04-01 15:00'),
        inspect_cleaning=get_test_cleaning(
            accepted_by=five_ago,
            completed_at=str_to_tz_dt('2018-04-01 12:00'),
            offered_start_time=str_to_tz_dt('2018-04-01 12:00')))
    for i in range(5):
      when = str_to_tz_dt('2018-05-01 12:00')
      when.replace(day=i + 1)
      get_test_cleaning(
          accepted_by=five_ago, completed_at=when, offered_start_time=when)
    twelve_ago = get_test_independent_worker()
    get_test_inspection(
        response=get_test_response(score=80),
        offered_start_time=str_to_tz_dt('2018-04-01 12:00'),
        inspect_cleaning=get_test_cleaning(
            accepted_by=twelve_ago,
            completed_at=str_to_tz_dt('2018-04-01 12:00'),
            offered_start_time=str_to_tz_dt('2018-04-01 12:00')))
    for i in range(12):
      when = str_to_tz_dt('2018-05-01 12:00')
      when.replace(day=i + 1)
      get_test_cleaning(
          accepted_by=twelve_ago, completed_at=when, offered_start_time=when)
    coming_up = get_test_independent_worker()
    get_test_inspection(
        offered_start_time=str_to_tz_dt('2018-11-01 12:00'),
        inspect_cleaning=get_test_cleaning(
            accepted_by=coming_up, completed_at=None,
            offered_start_time=str_to_tz_dt('2018-11-01 12:00')))

    NeedsInspectionScore.objects.assign_scores(
        nnow=str_to_tz_dt('2018-10-15 12:00'))

    self.assertEqual(2000000, never.needsinspectionscore.score)
    self.assertEqual(0, just_inspected.needsinspectionscore.score)
    self.assertEqual(1, score_not_submitted.needsinspectionscore.score)
    # round(5 / (0.9 ** 4)) == round(7.6) == 8
    self.assertEqual(8, five_ago.needsinspectionscore.score)
    # round(1000000 + 12 / (0.8 ** 4)) == round(1000029.3) == 1000029
    self.assertEqual(1000029, twelve_ago.needsinspectionscore.score)
    self.assertEqual(0, coming_up.needsinspectionscore.score)


class InspectionTests(TestCase):
  def test_cleaning_cancels(self):
    cleaning = get_test_cleaning()
    inspection = get_test_inspection(
        inspect_cleaning=cleaning,
        offered_start_time=str_to_tz_dt('2018-10-15 12:00'))
    self.assertEqual(CREATED, inspection.status())
    cleaning.was_canceled('This test wanted to cancel it.')
    inspection.refresh_from_db()
    self.assertEqual(CANCELED, inspection.status())

  def test_handle_response_and_get_cleaner_report(self):
    reservation = get_test_reservation(channel_id='HMRKWSFQKP')
    cleaner = get_test_independent_worker(name='Cleaner Ken')
    cleaning = get_test_cleaning(
        reservation=reservation, accepted_by=cleaner, all_tasks_complete=True,
        offered_start_time=str_to_tz_dt('2018-10-15 12:00'),
        started_at=str_to_tz_dt('2018-10-15 12:02'),
        completed_at=str_to_tz_dt('2018-10-15 14:00'))
    get_test_cleaning(  # Not started on time and not complete
        accepted_by=cleaner, all_tasks_complete=False,
        offered_start_time=str_to_tz_dt('2018-10-16 12:00'),
        started_at=str_to_tz_dt('2018-10-16 12:10'),
        completed_at=str_to_tz_dt('2018-10-16 14:00'))
    inspection = get_test_inspection(
        inspect_cleaning=cleaning,
        offered_start_time=str_to_tz_dt('2019-03-15 12:00'))

    self.assertEqual('HMRKWSFQKP', CLEANING_INSPECTION_RESPONSE[
        'form_response']['hidden']['reservation_id'])
    RawEvent.objects.create(
        json=json.dumps(CLEANING_INSPECTION_RESPONSE)).handle()

    inspection.refresh_from_db()
    self.assertEqual(0.47, inspection.get_score())

    expected = {
        'inspection_count': 1,
        'last_5_inspections': [inspection],
        'avg_total_score': 0.47,
        'overall_score': 4.0,
        'overall_specifics': 'Shades not all the way open (1)',
        'bathroom_score': 5.0,
        'bathroom_specifics': '',
        'kitchen_score': 2.0,
        'kitchen_specifics': (
            "Any dirty dishes (1), Coffee station not set up correctly (See "
            "Properly for photo) (1), Dishwasher isn't empty (1)"),
        'living_room_score': 5.0,
        'living_room_specifics': 'Any surfaces dirty (1)',
        'bedroom_score': 5.0,
        'bedroom_specifics': '',
        'cleaning_count': 2,
        'started_on_time': 1,
        'all_tasks': 1}
    self.assertEqual(expected, get_cleaner_report(cleaner))

    # As long as we're in here...
    self.login(is_superuser=True)
    url = reverse('cleaning_score', kwargs={'worker_pk': cleaner.pk})
    self.assert_get_contains(url, 'Cleaner Ken')

  def test_schedule(self):
    rental = get_test_rental()
    reservation = get_test_reservation(
        rental=rental, channel_id='hatersgonnahate',
        check_in=str_to_tz_dt('2018-10-15 16:00'),
        check_out=str_to_tz_dt('2018-10-16 11:00'))
    properly_rental = get_test_properly_rental(
        rental=rental, properly_property_id='oscarwildeshouse',
        source_property_id='oscarwildeshouse')
    get_test_cleaning_config(
        properly_rental=properly_rental, properly_checklist_id='charkloost',
        inspection_checklist_id='inparctloost', cleaning_duration=3)
    cleaner = get_test_independent_worker(
        name='Cleaner Cat', work_types=[CLEANER],
        buildings=[rental.building])
    cleaning = get_test_cleaning(
        reservation=reservation,
        offered_start_time=str_to_tz_dt('2018-10-16 11:15'),
        accepted_by=cleaner)
    inspector = get_test_independent_worker(
        name='Inspector Bond', email='bond@007.com',
        work_types=[CLEANING_INSPECTOR], buildings=[rental.building])

    api = Mock(spec=API)
    api.job_request_create.return_value = CREATE_JOB

    created = Inspection.objects.schedule(
        nnow=str_to_tz_dt('2018-10-11 12:00'), api=api)

    self.assertEqual(1, len(created))
    inspection = created[0]
    self.assertEqual(cleaning, inspection.inspect_cleaning)
    self.assertEqual(1, inspection.offered_to.count())
    self.assertEqual(
        inspector, inspection.offered_to.first().get_child_class_instance())
    self.assertIsNone(inspection.accepted_by)
    # creation_confirmed doesn't get set now until the webhook comes back.
    # Which it never does now because I'm ripping out Properly.
    self.assertIsNone(inspection.creation_confirmed)
    self.assertEqual(
        str_to_tz_dt('2018-10-16 15:00'), inspection.offered_start_time)

  def test_get_available_inspectors(self):
    building = get_test_building()
    accepted = get_test_independent_worker(
        name='Accepted', work_types=[CLEANING_INSPECTOR],
        buildings=[building])
    offered = get_test_independent_worker(
        name='Offered', work_types=[CLEANING_INSPECTOR],
        buildings=[building])
    available = get_test_independent_worker(
        name='Available', work_types=[CLEANING_INSPECTOR],
        buildings=[building])
    myself = get_test_independent_worker(
        name='Myself', work_types=[CLEANER, CLEANING_INSPECTOR],
        buildings=[building])
    rental = get_test_rental(building=building)
    cleaning = get_test_cleaning(
        accepted_by=myself,
        check_in=str_to_tz_dt('2018-10-14 16:00'),
        check_out=str_to_tz_dt('2018-10-15 11:00'),
        offered_start_time=str_to_tz_dt('2018-10-15 11:15'),
        rental=rental)
    get_test_cleaning_config(rental=rental)

    get_test_inspection(
        score=None, offered_start_time=str_to_tz_dt('2018-10-15 15:00'),
        accepted_by=accepted, offered_to=[accepted, offered, available],
        inspect_cleaning=get_test_cleaning(
            accepted_by=get_test_independent_worker(), rental=rental,
            offered_start_time=str_to_tz_dt('2018-10-15 11:15')))
    get_test_inspection(
        score=None, offered_start_time=str_to_tz_dt('2018-10-15 15:00'),
        accepted_by=None, offered_to=[offered],
        inspect_cleaning=get_test_cleaning(
            accepted_by=get_test_independent_worker(), rental=rental,
            offered_start_time=str_to_tz_dt('2018-10-15 11:15')))
    self.assertEqual(
        set([available]),
        set(Inspection.objects.get_available_inspectors(cleaning)))
