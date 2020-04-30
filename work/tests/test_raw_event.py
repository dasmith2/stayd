import copy
from datetime import timedelta
import json
from unittest.mock import Mock

from work.api import API
from work.api_examples import (
    ERROR_RESPONSE, CREATE_JOB, SET_SOURCE_PROPERTY_ID_RESPONSE,
    ACCEPTED_JOB_WEBHOOK, CANCELED_BY_CLEANER, CANCELED,
    JOB_STARTED, JOB_COMPLETE, JOB_COMPLETE_TASKS_INCOMPLETE,
    DECLINED_BY_WORKER)
from work.models.cleaning import Cleaning
from work.models.message import (
    MessageSender, Message, NOBODY_LEFT_TO_DO_A_JOB, EMAIL)
from work.models.raw_event import RawEvent
from work.models.work import (
    CANCELED as CANCELED_STATUS, CanceledOrDeclined)
from work.models.work_type import CLEANER
from work.tests.test_cleaning import (
    get_test_cleaning_config, get_test_cleaning)
from work.tests.test_work import get_test_independent_worker
from rentals.tests import get_test_building, get_test_rental
from reservations.tests import get_test_reservation
from util.email import EmailSender
from util.html_status_codes import NotOkError
from util.tests import TestCase
from util.timezone import str_to_tz_dt, now


def get_test_raw_event(**kwargs):
  return RawEvent.objects.create(
      json=kwargs.get('json', '{"hello": "world"}'),
      created_at=kwargs.get('created_at', str_to_tz_dt('2018-10-15 12:00')),
      handled_at=kwargs.get('handled_at', str_to_tz_dt('2018-10-15 12:01')),
      event_name=kwargs.get('event_name', 'jobRequest.create'),
      work=kwargs.get('work', None))


class AcceptStartEndTests(TestCase):
  def test_accept_start_end(self):
    worker = get_test_independent_worker(
        worker_id='test_worker_id', email='nikolagirl@yahoo.com')
    cleaning = get_test_cleaning(job_request_id='5cffe19414b48ac5b66f1fce')
    get_test_cleaning_config(rental=cleaning.reservation.rental)
    accept_hook = copy.deepcopy(ACCEPTED_JOB_WEBHOOK)
    accept_hook['createdAt'] = '2018-01-08T11:10:00.000Z'
    start_hook = copy.deepcopy(JOB_STARTED)
    if not start_hook['results'][0]['jobRequestId']:
      raise Exception()  # Just making sure the field names didn't change.
    start_hook['results'][0]['jobRequestId'] = '5cffe19414b48ac5b66f1fce'
    start_hook['createdAt'] = '2018-01-08T11:20:00.000Z'
    # Properly is known to send us multiple started webhooks for the same job!
    start_hook_2 = copy.deepcopy(JOB_STARTED)
    start_hook_2['results'][0]['jobRequestId'] = '5cffe19414b48ac5b66f1fce'
    start_hook_2['createdAt'] = '2018-01-08T12:20:00.000Z'
    complete_hook = copy.deepcopy(JOB_COMPLETE)
    complete_hook['createdAt'] = '2018-01-08T13:25:00.000Z'

    complete_hook_unfinished = copy.deepcopy(JOB_COMPLETE_TASKS_INCOMPLETE)
    complete_hook_unfinished['results'][0]['jobRequestId'] = (
        '5cffe19414b48ac5b66f1fce')

    RawEvent.objects.create(json=json.dumps(accept_hook)).handle()
    RawEvent.objects.create(json=json.dumps(start_hook)).handle()
    RawEvent.objects.create(json=json.dumps(start_hook_2)).handle()
    raw_complete = RawEvent.objects.create(json=json.dumps(complete_hook))
    raw_complete.handle()

    cleaning.refresh_from_db()

    self.assertTrue(cleaning.action_on_properly)
    self.assertEqual(worker, cleaning.accepted_by.get_child_class_instance())
    self.assertEqual(
        str_to_tz_dt('2018-01-08 11:10', tz_str='UTC'), cleaning.accepted_at)
    self.assertEqual(
        str_to_tz_dt('2018-01-08 11:20', tz_str='UTC'), cleaning.started_at)
    self.assertEqual(
        str_to_tz_dt('2018-01-08 13:25', tz_str='UTC'),
        cleaning.completed_at)
    cleaning.refresh_from_db()
    self.assertTrue(cleaning.all_tasks_complete)

    cleaning.completed_at = None
    cleaning.save()
    RawEvent.objects.create(json=json.dumps(complete_hook_unfinished)).handle()
    cleaning.refresh_from_db()
    self.assertFalse(cleaning.all_tasks_complete)


class RawEventTests(TestCase):
  def test_unknown_service_worker_id_accepts_job(self):
    raw = get_test_raw_event()
    work = get_test_cleaning()
    email_sender = Mock(spec=EmailSender)
    message_sender = MessageSender(email_sender=email_sender)
    for i in range(2):
      raw.handle_accepted_job_request(
          work, 'does_not_exist@workeremail.com', message_sender, None, None)
    self.assertIsNone(raw.worker)

  def test_job_request_canceled_completed(self):
    # One time we got a cancel webhook for a completed job. I hypothesize there
    # was a properly bug that continued to show the job so to try to get it off
    # their list, the service provicer canceled it.
    cleaning = get_test_cleaning(
        job_request_id='blue',
        started_at=str_to_tz_dt('2018-12-25 11:15'),
        completed_at=str_to_tz_dt('2018-12-25 14:05'),
        permanently_canceled_reason='')
    get_test_cleaning_config(rental=cleaning.reservation.rental)
    hook = copy.deepcopy(CANCELED)
    hook['results'][0]['jobRequestId'] = 'blue'

    # By virtue of using a real API which raises exceptions in tests when you
    # make it do anything, I'm testing that it does nothing.
    RawEvent.objects.create(json=json.dumps(hook)).handle()

    cleaning.refresh_from_db()
    self.assertIsNone(cleaning.canceled_at)
    self.assertEqual('', cleaning.permanently_canceled_reason)

  def test_job_request_canceled_known(self):
    cleaning = get_test_cleaning(
        job_request_id='blue',
        canceled_at=str_to_tz_dt('2018-10-15 12:00'),
        permanently_canceled_reason='The blargh blarghed too hard!')
    get_test_cleaning_config(rental=cleaning.reservation.rental)
    hook = copy.deepcopy(CANCELED)
    hook['results'][0]['jobRequestId'] = 'blue'

    api = Mock(spec=API)
    api.job_request_create.return_value = CREATE_JOB
    raw = RawEvent.objects.create(json=json.dumps(hook))
    raw.handle(api=api)

    cleaning.refresh_from_db()
    self.assertEqual(
        'The blargh blarghed too hard!', cleaning.permanently_canceled_reason)
    self.assertEqual(0, len(api.job_request_create.call_args_list))

  def test_job_request_canceled_unknown(self):
    reservation = get_test_reservation(
        check_in=now() + timedelta(days=1),
        check_out=now() + timedelta(days=1), id_verified=True)
    cleaning = get_test_cleaning(
        job_request_id='blue', reservation=reservation)
    get_test_cleaning_config(rental=reservation.rental)
    get_test_independent_worker(
        buildings=[reservation.rental.building], work_types=[CLEANER])
    hook = copy.deepcopy(CANCELED)
    hook['results'][0]['jobRequestId'] = 'blue'

    self.assertFalse(cleaning.canceled_at)

    api = Mock(spec=API)
    api.job_request_create.return_value = CREATE_JOB
    raw = RawEvent.objects.create(json=json.dumps(hook))
    raw.handle(api=api)

    cleaning.refresh_from_db()
    self.assertFalse(cleaning.canceled_at)  # Because it was rescheduled.
    self.assertEqual('', cleaning.permanently_canceled_reason)

  def test_job_request_canceled_by_cleaner(self):
    building = get_test_building()
    reservation = get_test_reservation(
        check_in=now() + timedelta(days=1),
        check_out=now() + timedelta(days=1), id_verified=True,
        building=building)
    original_accepted_by = get_test_independent_worker(
        name='Delete Daren', buildings=[building], work_types=[CLEANER])
    cleaning = get_test_cleaning(
        job_request_id='blue', reservation=reservation,
        accepted_by=original_accepted_by, building=building)
    get_test_cleaning_config(rental=cleaning.reservation.rental)
    # Somebody new to assign it to.
    get_test_independent_worker(buildings=[building], work_types=[CLEANER])

    hook = copy.deepcopy(CANCELED_BY_CLEANER)
    hook['results'][0]['jobRequestId'] = 'blue'

    api = Mock(spec=API)
    api.job_request_create.return_value = CREATE_JOB

    raw = RawEvent.objects.create(json=json.dumps(hook))
    raw.handle(api=api)

    raw.refresh_from_db()
    self.assertEqual(
        original_accepted_by, raw.worker.get_child_class_instance())
    cleaning.refresh_from_db()
    self.assertFalse(cleaning.canceled_at)  # Because it rescheduled.
    self.assertEqual('', cleaning.permanently_canceled_reason)

    new_cleaning = Cleaning.objects.get(
        reservation=cleaning.reservation, canceled_at__isnull=True)
    self.assertEqual(cleaning, new_cleaning)
    CanceledOrDeclined.objects.get(work=cleaning, worker=original_accepted_by)
    self.assertFalse(original_accepted_by.pk in set(
        [worker.pk for worker in new_cleaning.offered_to.all()]))
    self.assertIsNone(new_cleaning.accepted_by)

  def test_job_request_declined_by_worker(self):
    worker = get_test_independent_worker(
        name='Decline Dave', worker_id='dSZnGjhNRE',
        email='cosmapollo@gmail.com')
    work = get_test_cleaning(
        job_request_id='5cffd016c75ec5a2ae5aa3e5', accepted_by=worker)
    RawEvent.objects.create(
        json=json.dumps(DECLINED_BY_WORKER)).handle(api=Mock(spec=API))
    CanceledOrDeclined.objects.get(worker=worker, work=work)

  def test_job_request_canceled_action_on_keys(self):
    cleaning = get_test_cleaning(
        job_request_id='blue',
        action_on_keys=True)
    hook = copy.deepcopy(CANCELED)
    hook['results'][0]['jobRequestId'] = 'blue'

    api = Mock(spec=API)
    api.job_request_create.return_value = CREATE_JOB
    raw = RawEvent.objects.create(json=json.dumps(hook))
    raw.handle(api=api)

    cleaning.refresh_from_db()

  def test_job_request_accepted_causes_no_workers_available_on_other_job(self):
    build = get_test_building(alerts_email='bad@things.happened')
    bob = get_test_independent_worker(
        name='Bob Bill', email='nikolagirl@yahoo.com', worker_id='boopbapbip',
        buildings=[build])
    rental_1 = get_test_rental(building=build, nickname='Casa de Davo')
    rental_2 = get_test_rental(building=build, nickname='Casa de Stevo')
    get_test_cleaning_config(building=build, rental=rental_1)
    get_test_cleaning_config(building=build, rental=rental_2)
    res_1 = get_test_reservation(
        check_in=str_to_tz_dt('2018-05-15 16:00'),
        check_out=str_to_tz_dt('2018-05-16 11:00'), rental=rental_1)
    res_2 = get_test_reservation(
        check_in=str_to_tz_dt('2018-05-15 16:00'),
        check_out=str_to_tz_dt('2018-05-16 11:00'), rental=rental_2)
    get_test_cleaning(
        job_request_id='5cffe19414b48ac5b66f1fce', offered_to=[bob],
        reservation=res_1, creation_confirmed=str_to_tz_dt('2018-05-15'))
    clean_2 = get_test_cleaning(
        job_request_id='job_2', offered_to=[bob], reservation=res_2,
        creation_confirmed=str_to_tz_dt('2018-05-15'))

    api = Mock(spec=API)

    RawEvent.objects.create(
        json=json.dumps(ACCEPTED_JOB_WEBHOOK)).handle(api=api)

    clean_2.refresh_from_db()
    self.assertEqual(CANCELED_STATUS, clean_2.status())
    content = (
        'Bob Bill accepted a cleaning at Casa de Davo on 2018-05-16. So far '
        'so good. BUT! There\'s a cleaning at Casa de Stevo on 2018-05-16 '
        'that was only offered to Bob Bill, so now there\'s nobody left to '
        'do that job, so I canceled it.')
    message = Message.objects.get(
        to='bad@things.happened', reason=NOBODY_LEFT_TO_DO_A_JOB, kind=EMAIL,
        subject=NOBODY_LEFT_TO_DO_A_JOB, work=clean_2)
    self.assertEqual(content, message.content)


class JobRequestAcceptedByCleanerWithIdTests(TestCase):
  def test_job_request_accepted_by_cleaner_with_id(self):
    build = get_test_building()
    bob = get_test_independent_worker(
        name='Bob Bill', email='nikolagirl@yahoo.com', worker_id='boopbapbip',
        buildings=[build])
    fatima = get_test_independent_worker(
        name='Fatima Sur', email='fatima@sur.com', buildings=[build],
        worker_id='smorkinborkin')
    check_1 = get_test_cleaning_config(building=build)
    check_2 = get_test_cleaning_config(building=build)
    res_1 = get_test_reservation(
        check_in=str_to_tz_dt('2018-05-15 16:00'),
        check_out=str_to_tz_dt('2018-05-16 11:00'),
        rental=check_1.properly_rental.rental)
    res_2 = get_test_reservation(
        check_in=str_to_tz_dt('2018-05-15 16:00'),
        check_out=str_to_tz_dt('2018-05-16 11:00'),
        rental=check_2.properly_rental.rental)
    clean_1 = get_test_cleaning(
        job_request_id='5cffe19414b48ac5b66f1fce', offered_to=[bob, fatima],
        reservation=res_1)
    clean_2 = get_test_cleaning(
        job_request_id='job_2', offered_to=[bob, fatima],
        reservation=res_2)

    self.assertEqual(clean_1.get_start_time(), clean_2.get_start_time())

    api = Mock(spec=API)

    raw = RawEvent.objects.create(json=json.dumps(ACCEPTED_JOB_WEBHOOK))
    self.assertFalse(bool(raw.handled_at))
    raw.handle(api=api)
    raw.refresh_from_db()

    self.assertTrue(bool(raw.handled_at))
    self.assertEqual('jobRequest.accepted', raw.event_name)
    self.assertEqual(bob, raw.worker.get_child_class_instance())

    clean_1.refresh_from_db()
    clean_2.refresh_from_db()

    self.assertEqual(bob, clean_1.accepted_by.get_child_class_instance())
    self.assertIsNone(clean_2.accepted_by)
    self.assertEqual(1, clean_2.offered_to.count())
    self.assertEqual(
        fatima, clean_2.offered_to.all()[0].get_child_class_instance())


class APITests(TestCase):
  def test_check_response_data_is_ok(self):
    api = API()
    try:
      api.check_response_data_is_ok({}, ERROR_RESPONSE)
      self.fail('An exception should have happened.')
    except NotOkError:
      pass
    api.check_response_data_is_ok({}, CREATE_JOB)
    api.check_response_data_is_ok({}, SET_SOURCE_PROPERTY_ID_RESPONSE)
