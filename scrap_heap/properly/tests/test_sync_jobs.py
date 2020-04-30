import copy
import json
from unittest.mock import Mock, call

from django.utils.dateparse import parse_datetime

from work.api import API
from work.api_examples import (
    CLEANING_JOBS_KICK_OFF, CLEANING_JOBS_RESULTS, CREATE_JOB)
from work.models.one_off import OneOff
from work.models.raw_event import RawEvent
from work.models.sync_jobs import (
    trigger_sync_jobs, CANCELLED_STATUS,
    CANCELLED_BY_SERVICE_PROVIDER_STATUS)
from work.models.work import CanceledOrDeclined
from work.tests.test_cleaning import (
    get_test_cleaning, get_test_cleaning_config)
from work.tests.test_rental import get_test_properly_rental
from work.tests.test_worker import get_test_independent_worker
from rentals.tests import get_test_building, get_test_rental
from util.tests import TestCase
from util.timezone import str_to_tz_dt


class SyncJobsTests(TestCase):
  def test_trigger_sync_jobs(self):
    api = Mock(spec=API)
    api.cleaning_jobs.return_value = CLEANING_JOBS_KICK_OFF
    trigger_sync_jobs(
        str_to_tz_dt('2018-12-25'), str_to_tz_dt('2018-12-26'), api=api)
    call_data = {'filters': {
        'dateFrom': '2018-12-25T05:00:00Z', 'dateTo': '2018-12-26T05:00:00Z'}}
    self.assertEqual([call(call_data)], api.cleaning_jobs.call_args_list)

  def test_do_sync_jobs_exist(self):
    bob = get_test_independent_worker(
        worker_id='dSZnGjhNRE', name='Bob', email='naijshua@gmail.com')
    cleaning = get_test_cleaning(job_request_id='5cb375685322e58586eddbe7')

    RawEvent.objects.create(json=json.dumps(CLEANING_JOBS_RESULTS)).handle()

    cleaning.refresh_from_db()
    self.assertEqual(
        parse_datetime('2019-04-14T18:11:11.975Z'),
        cleaning.offered_start_time)
    self.assertEqual(
        parse_datetime('2019-04-14T18:43:00.660Z'), cleaning.completed_at)
    self.assertEqual(
        parse_datetime('2019-04-14T18:28:31.413Z'), cleaning.started_at)
    self.assertEqual(bob, cleaning.accepted_by.get_child_class_instance())
    self.assertTrue(cleaning.action_on_properly)

  def test_do_sync_jobs_do_not_exist(self):
    bob = get_test_independent_worker(
        worker_id='dSZnGjhNRE', name='Bob', email='naijshua@gmail.com')
    properly_rental = get_test_properly_rental(
        properly_property_id='xrhoa71I8t', source_property_id='xrhoa71I8t')

    RawEvent.objects.create(json=json.dumps(CLEANING_JOBS_RESULTS)).handle()

    one_off = OneOff.objects.get(
        accepted_by=bob,
        job_request_id='5cb375685322e58586eddbe7',
        started_at=parse_datetime('2019-04-14T18:28:31.413Z'),
        accepted_at=parse_datetime('2019-04-14T18:11:11.975Z'),
        completed_at=parse_datetime('2019-04-14T18:43:00.660Z'),
        offered_start_time=parse_datetime('2019-04-14T18:11:11.975Z'),
        title='Unknown',
        message='The properly API doesn\'t tell us what this job is.',
        properly_rental=properly_rental)
    self.assertTrue(one_off.workpayment.on_hold_reason)

  def test_accepted_clears_out_creation_error_sets_worker_id(self):
    # cleanables_require_create_in_keys assumes that if there's a creation
    # error then the cleaning wasn't created. But if it turns out that the
    # cleaning was accepted, I guess it got created after all, didn't it. So in
    # that case clear out the error.
    building = get_test_building()
    rental = get_test_rental(building=building)
    get_test_cleaning_config(rental=rental)
    bob = get_test_independent_worker(
        worker_id='incorrect_id_here', name='Bob', email='naijshua@gmail.com')
    cleaning = get_test_cleaning(
        job_request_id='5cb375685322e58586eddbe7',
        check_in=str_to_tz_dt('2019-01-01 16:00'),
        check_out=str_to_tz_dt('2019-01-02 11:00'), id_verified=True,
        rental=rental, creation_error='Creation went dreadfully wrong.')

    api = Mock(spec=API)
    api.job_request_create.return_value = CREATE_JOB
    RawEvent.objects.create(json=json.dumps(CLEANING_JOBS_RESULTS)).handle(
        api=api, nnow=str_to_tz_dt('2018-12-28'))

    cleaning.refresh_from_db()
    bob.refresh_from_db()
    self.assertEqual('dSZnGjhNRE', bob.worker_id)
    self.assertEqual(bob, cleaning.accepted_by.get_child_class_instance())
    self.assertEqual('', cleaning.creation_error)

  def test_sync_canceled_job(self):
    building = get_test_building()
    rental = get_test_rental(building=building)
    get_test_independent_worker(buildings=[building])
    get_test_cleaning_config(rental=rental)
    cleaning = get_test_cleaning(
        job_request_id='5cb375685322e58586eddbe7',
        check_in=str_to_tz_dt('2019-01-01 16:00'),
        check_out=str_to_tz_dt('2019-01-02 11:00'), id_verified=True,
        rental=rental)

    result = copy.deepcopy(CLEANING_JOBS_RESULTS)
    result['results'][0]['status'] = CANCELLED_STATUS
    api = Mock(spec=API)
    api.job_request_create.return_value = CREATE_JOB
    RawEvent.objects.create(json=json.dumps(result)).handle(
        api=api, nnow=str_to_tz_dt('2018-12-28'))

    cleaning.refresh_from_db()
    # This is the new id from CREATE_JOB because it rescheduled.
    self.assertEqual('5bce266701ff159cd2e21656', cleaning.job_request_id)
    self.assertEqual(1, len(api.job_request_create.call_args_list))

  def test_sync_canceled_by_service_provider(self):
    building = get_test_building()
    rental = get_test_rental(building=building)
    get_test_independent_worker(buildings=[building])
    get_test_cleaning_config(rental=rental)
    jane = get_test_independent_worker(
        buildings=[building], worker_id='dSZnGjhNRE',
        email='naijshua@gmail.com')
    cleaning = get_test_cleaning(
        job_request_id='5cb375685322e58586eddbe7',
        check_in=str_to_tz_dt('2019-01-01 16:00'),
        check_out=str_to_tz_dt('2019-01-02 11:00'), id_verified=True,
        rental=rental, accepted_by=jane)

    result = copy.deepcopy(CLEANING_JOBS_RESULTS)
    result['results'][0]['status'] = CANCELLED_BY_SERVICE_PROVIDER_STATUS
    api = Mock(spec=API)
    api.job_request_create.return_value = CREATE_JOB
    RawEvent.objects.create(json=json.dumps(result)).handle(
        api=api, nnow=str_to_tz_dt('2018-12-28'))

    cleaning.refresh_from_db()
    # This is the new id from CREATE_JOB because it rescheduled.
    self.assertEqual('5bce266701ff159cd2e21656', cleaning.job_request_id)
    CanceledOrDeclined.objects.get(worker=jane, work=cleaning)
