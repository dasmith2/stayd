import copy
from datetime import timedelta, date, datetime
from dateutil.parser import parse
from decimal import Decimal
import json
from unittest.mock import Mock, call

from django.utils.timezone import now, make_aware
from djmoney.money import Money

from front.models import Front, FakeSendSMSResult
from properly.api import API
from properly.api_examples import (
    ERROR_RESPONSE, CREATE_JOB, SET_SOURCE_PROPERTY_ID_RESPONSE, CANCEL_JOB,
    ACCEPTED_JOB_WEBHOOK, CANCELED_BY_CLEANER, JOB_STARTED, JOB_COMPLETE,
    BOOKING_CREATE)
from properly.models.cleaning import (
    Booking, Cleaner, Cleaning, RentalChecklist, Checklist, HoursAndPayRow,
    RawEvent)
from properly.models.message_sender import MessageSender
from properly.models.messages import (
    SubjectLine, Message,
    UNCLAIMED_CLEANING_IN_LT_48_HOURS, GOOD_MORNING_TODAYS_JOBS,
    START_10_MINUTES_LATE)
from rentals.tests import get_test_rental, get_test_building
from reservations.models import Reservation, CANCELED
from reservations.tests import get_test_reservation
from util.email import EmailSender
from util.network import CantUseTheNet
from util.signals import post_sync
from util.tests import TestCase, FakeResponse
from util.timezone import str_to_tz_dt


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


def get_test_booking(create, **kwargs):
  reservation = kwargs.get('reservation', None)
  if not reservation:
    reservation = get_test_reservation(True, **kwargs)
  booking = Booking(
      booking_id=kwargs.get('booking_id', 'whatever1234'),
      reservation=reservation)
  if create:
    booking.save()
  return booking


def get_test_cleaning(create, **kwargs):
  reservation = kwargs.get('reservation', None)
  if not reservation:
    reservation = get_test_reservation(True, **kwargs)
  cleaning = Cleaning(
      accepted_by=kwargs.get('accepted_by', None),
      reservation=reservation,
      job_request_id=kwargs.get('job_request_id', None),
      creation_confirmed=kwargs.get('creation_confirmed', None),
      started_at=kwargs.get('started_at', None),
      completed_at=kwargs.get('completed_at', None),
      offered_start_time=kwargs.get(
          'offered_start_time', reservation.check_out + timedelta(minutes=15)))
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
      source_property_id=kwargs.get('source_property_id', 'blarginblorg'))
  if create:
    rental_checklist.save()
  return rental_checklist


def get_test_subject_line(create, **kwargs):
  subject_line = SubjectLine(
      reason=kwargs.get('reason', UNCLAIMED_CLEANING_IN_LT_48_HOURS),
      subject=kwargs.get('subject', 'Warning: unclaimed cleaning'))
  if create:
    subject_line.save()
  return subject_line


class WebhookTests(TestCase):
  def test_start_end(self):
    cleaning = get_test_cleaning(True, job_request_id='green')
    start_hook = copy.deepcopy(JOB_STARTED)
    start_hook['results'][0]['jobRequestId'] = 'green'
    start_hook['createdAt'] = '2018-01-08T11:20:00.000Z'
    complete_hook = copy.deepcopy(JOB_COMPLETE)
    complete_hook['results'][0]['jobRequestId'] = 'green'
    complete_hook['createdAt'] = '2018-01-08T13:25:00.000Z'

    RawEvent.objects.create(json=json.dumps(start_hook)).handle()
    RawEvent.objects.create(json=json.dumps(complete_hook)).handle()

    cleaning.refresh_from_db()

    self.assertEqual(
        str_to_tz_dt('2018-01-08 11:20', tz_str='UTC'), cleaning.started_at)
    self.assertEqual(
        str_to_tz_dt('2018-01-08 13:25', tz_str='UTC'),
        cleaning.completed_at)

  def test_job_request_canceled_by_cleaner(self):
    cleaning = get_test_cleaning(True, job_request_id='blue')
    get_test_booking(True, reservation=cleaning.reservation)
    get_test_rental_checklist(True, rental=cleaning.reservation.rental)

    hook = copy.deepcopy(CANCELED_BY_CLEANER)
    hook['results'][0]['jobRequestId'] = 'blue'

    api = Mock(spec=API)
    api.job_request_create.return_value = FakeResponse(True, CREATE_JOB)

    raw = RawEvent.objects.create(json=json.dumps(hook))
    raw.handle(api=api)

    self.assertEqual([call('blue')], api.job_request_cancel.call_args_list)
    self.assertEqual(1, len(api.job_request_create.call_args_list))
    new_cleaning = Cleaning.objects.get(reservation=cleaning.reservation)
    self.assertEqual('5bce266701ff159cd2e21656', new_cleaning.job_request_id)
    self.assertIsNone(new_cleaning.accepted_by)

  def test_job_request_accepted(self):
    build = get_test_building(True)
    bob = get_test_cleaner(
        True, name='Bob Bill', email='bob@bill.boing', buildings=[build])
    fatima = get_test_cleaner(
        True, name='Fatima Sur', email='fatima@sur.com', buildings=[build])
    check_1 = get_test_rental_checklist(True, building=build)
    check_2 = get_test_rental_checklist(True, building=build)
    res_1 = get_test_reservation(
        True, check_in=str_to_tz_dt('2018-05-15 16:00'),
        check_out=str_to_tz_dt('2018-05-16 11:00'), rental=check_1.rental)
    res_2 = get_test_reservation(
        True, check_in=str_to_tz_dt('2018-05-15 16:00'),
        check_out=str_to_tz_dt('2018-05-16 11:00'), rental=check_2.rental)
    clean_1 = get_test_cleaning(
        True, job_request_id='job_1', offered_to=[bob, fatima],
        reservation=res_1)
    clean_2 = get_test_cleaning(
        True, job_request_id='job_2', offered_to=[bob, fatima],
        reservation=res_2)

    self.assertEqual(clean_1.get_start_time(), clean_2.get_start_time())

    hook = copy.deepcopy(ACCEPTED_JOB_WEBHOOK)
    hook['results'][0]['jobRequestId'] = 'job_1'
    hook['results'][0]['serviceProvider'] = 'bob@bill.boing'

    api = Mock(spec=API)

    raw = RawEvent.objects.create(json=json.dumps(hook))
    self.assertFalse(bool(raw.handled_at))
    raw.handle(api=api)
    raw.refresh_from_db()

    self.assertTrue(bool(raw.handled_at))

    clean_1.refresh_from_db()
    clean_2.refresh_from_db()

    self.assertEqual(bob, clean_1.accepted_by)
    self.assertIsNone(clean_2.accepted_by)
    self.assertEqual([fatima], list(clean_2.offered_to.all()))

    expected_data = {
        'jobRequestId': 'job_2',
        'changes': {'serviceProviders': [{'email': 'fatima@sur.com'}]}}
    self.assertEqual(
        [call(expected_data)], api.job_request_update.call_args_list)


class CleaningTests(TestCase):
  def test_taking_too_long(self):
    get_test_cleaning(  # yesterday
        True, check_in=str_to_tz_dt('2018-05-15 16:00'),
        check_out=str_to_tz_dt('2018-05-16 11:00'),
        started_at=str_to_tz_dt('2018-05-16 11:15'),
        completed_at=str_to_tz_dt('2018-05-16 19:15'),
        accepted_by=get_test_cleaner(True))
    get_test_cleaning(  # in progress but not too long
        True, check_in=str_to_tz_dt('2018-05-15 16:00'),
        check_out=str_to_tz_dt('2018-05-17 11:00'),
        started_at=str_to_tz_dt('2018-05-17 11:30'),
        completed_at=None,
        accepted_by=get_test_cleaner(True))
    in_progress_too_long = get_test_cleaning(
        True, check_in=str_to_tz_dt('2018-05-15 16:00'),
        check_out=str_to_tz_dt('2018-05-17 11:00'),
        started_at=str_to_tz_dt('2018-05-17 11:15'),
        completed_at=None,
        accepted_by=get_test_cleaner(True))
    self.assertFalse(in_progress_too_long.is_complete())
    get_test_cleaning(  # complete but not too long
        True, check_in=str_to_tz_dt('2018-05-15 16:00'),
        check_out=str_to_tz_dt('2018-05-17 11:00'),
        started_at=str_to_tz_dt('2018-05-17 11:30'),
        completed_at=str_to_tz_dt('2018-05-17 13:30'),
        accepted_by=get_test_cleaner(True))
    complete_too_long = get_test_cleaning(
        True, check_in=str_to_tz_dt('2018-05-15 16:00'),
        check_out=str_to_tz_dt('2018-05-17 11:00'),
        started_at=str_to_tz_dt('2018-05-17 11:16'),
        completed_at=str_to_tz_dt('2018-05-17 14:50'),
        accepted_by=get_test_cleaner(True))
    self.assertTrue(complete_too_long.is_complete())
    nnow = str_to_tz_dt('2018-05-17 14:55')
    self.assertEqual(
        [in_progress_too_long, complete_too_long],
        Cleaning.objects.taking_too_long(nnow))

  def test_overlapping(self):
    cleaner_1 = get_test_cleaner(True)
    first = get_test_cleaning(
        True, accepted_by=cleaner_1,
        offered_start_time=str_to_tz_dt('2018-05-15 11:15'))
    overlap = get_test_cleaning(
        True, accepted_by=cleaner_1,
        offered_start_time=str_to_tz_dt('2018-05-15 11:15'))
    get_test_cleaning(  # Different day
        True, accepted_by=cleaner_1,
        offered_start_time=str_to_tz_dt('2018-05-16 11:15'))
    get_test_cleaning(  # Different cleaner
        True, accepted_by=get_test_cleaner(True),
        offered_start_time=str_to_tz_dt('2018-05-15 11:15'))
    no_cleaner_1 = get_test_cleaning(
        True, accepted_by=None,
        offered_start_time=str_to_tz_dt('2018-05-15 11:15'))
    get_test_cleaning(
        True, accepted_by=None,
        offered_start_time=str_to_tz_dt('2018-05-15 11:15'))
    self.assertEqual([overlap], list(first.overlapping()))
    self.assertEqual([], no_cleaner_1.overlapping())

  def test_hours_and_pay(self):
    cleaninator = get_test_cleaner(
        True, name='Cleaninator', hourly_rate=Money('15.0', 'USD'))
    cleanasaur = get_test_cleaner(
        True, name='Cleanasaur', hourly_rate=Money('12.0', 'USD'))
    get_test_cleaner(
        True, name='Dirty', hourly_rate=Money('5.0', 'USD'))
    started_1 = str_to_tz_dt('2018-10-05 11:17')
    started_2 = str_to_tz_dt('2018-10-06 11:17')
    started_no = str_to_tz_dt('2018-10-11 11:17')

    get_test_cleaning(  # yep
        True, accepted_by=cleaninator, started_at=started_1,
        completed_at=started_1 + timedelta(hours=2))
    get_test_cleaning(  # yep
        True, accepted_by=cleaninator, started_at=started_2,
        completed_at=started_2 + timedelta(hours=1))
    get_test_cleaning(  # nope
        True, accepted_by=cleaninator, started_at=started_no,
        completed_at=started_no + timedelta(hours=4))

    get_test_cleaning(  # yep
        True, accepted_by=cleanasaur, started_at=started_1,
        completed_at=started_1 + timedelta(hours=3))

    hours_and_pay = Cleaning.objects.hours_and_pay(
        date(2018, 10, 5), date(2018, 10, 10))
    self.assertEqual(2, len(hours_and_pay))
    self.assertEqual(
        HoursAndPayRow('Cleanasaur', 1, 3, Decimal('12.0'), Decimal('36.0')),
        hours_and_pay[0])
    self.assertEqual(
        HoursAndPayRow('Cleaninator', 2, 3, Decimal('15.0'), Decimal('45.0')),
        hours_and_pay[1])

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
        True, check_out=now() + timedelta(hours=1), id_verified=True,
        balance_due=Money('0.0', 'USD'))
    yes_2 = get_test_reservation(
        True, check_out=now() + timedelta(days=6), id_verified=True,
        balance_due=Money('0.0', 'USD'))
    has_a_cleaning_already = get_test_reservation(
        True, check_out=now() + timedelta(days=6), id_verified=True,
        balance_due=Money('0.0', 'USD'))
    get_test_cleaning(True, reservation=has_a_cleaning_already)
    get_test_reservation(
        True, check_out=now() + timedelta(days=8), id_verified=True,
        balance_due=Money('0.0', 'USD'))  # Too distant
    get_test_reservation(  # ID not verified
        True, check_out=now() + timedelta(hours=1), id_verified=False,
        balance_due=Money('0.0', 'USD'))
    get_test_reservation(  # Not paid in full
        True, check_out=now() + timedelta(hours=1), id_verified=True,
        balance_due=Money('100', 'USD'))
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
        properly_rental_id='daves_source_id',
        source_property_id='daves_source_id')
    reservation = get_test_reservation(
        True, check_out=parse('2018-10-28T15:00:00.000Z'),
        channel_reservation_id='ibelieveinafingcalledlove',
        rental=rental, id_verified=True, balance_due=Money('0.0', 'USD'))
    get_test_booking(True, reservation=reservation)
    api = Mock(spec=API)
    api.job_request_create.return_value = FakeResponse(True, CREATE_JOB)

    cleanings = Cleaning.objects.create_job_requests(
        api=api, nnow=str_to_tz_dt('2018-10-27 12:00'))

    self.assertEqual(1, len(cleanings))
    cleaning = cleanings[0]
    self.assertTrue(bool(cleaning.creation_confirmed))
    self.assertEqual(cleaning.job_request_id, '5bce266701ff159cd2e21656')
    self.assertEqual(cleaning.get_start_time(), cleaning.offered_start_time)
    self.assertEqual(
        parse('2018-10-28T15:15:00.000Z'), cleaning.get_start_time())

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

  def test_todays_cleanings(self):
    today = date.today()
    cleaner = get_test_cleaner(True)
    yes = get_test_cleaning(
        True, accepted_by=cleaner, reservation=get_test_reservation(
            True, check_out=make_aware(datetime(
                today.year, today.month, today.day, 11))))
    get_test_cleaning(  # Wrong day
        True, accepted_by=cleaner, reservation=get_test_reservation(
            True, check_out=make_aware(timedelta(days=1) + datetime(
                today.year, today.month, today.day, 11))))
    get_test_cleaning(  # No cleaner
        True, accepted_by=None, reservation=get_test_reservation(
            True, check_out=make_aware(datetime(
                today.year, today.month, today.day, 11))))
    self.assertEqual([yes], list(Cleaning.objects.todays_cleanings()))

  def test_uh_oh_unclaimed(self):
    cleaning = get_test_cleaning(
        True, accepted_by=None, reservation=get_test_reservation(
            True, check_out=str_to_tz_dt('2018-10-17 11:00')))
    Cleaning.objects.filter(pk=cleaning.pk).update(
        created_at=str_to_tz_dt('2018-10-15 08:00'))
    self.assertEqual([], list(Cleaning.objects.uh_oh_unclaimed(
        nnow=str_to_tz_dt('2018-10-15 11:14'))))
    self.assertEqual([cleaning], list(Cleaning.objects.uh_oh_unclaimed(
        nnow=str_to_tz_dt('2018-10-15 11:16'))))
    cleaning.accepted_by = get_test_cleaner(True)
    cleaning.save()
    self.assertEqual([], list(Cleaning.objects.uh_oh_unclaimed(
        nnow=str_to_tz_dt('2018-10-15 11:16'))))
    Cleaning.objects.filter(pk=cleaning.pk).update(
        accepted_by=None, created_at=str_to_tz_dt('2018-10-15 10:00'))
    self.assertEqual([], list(Cleaning.objects.uh_oh_unclaimed(
        nnow=str_to_tz_dt('2018-10-15 12:59'))))
    self.assertEqual([cleaning], list(Cleaning.objects.uh_oh_unclaimed(
        nnow=str_to_tz_dt('2018-10-15 13:00'))))

  def test_reservation_checkout_changes(self):
    reservation = get_test_reservation(
        True, check_in=str_to_tz_dt('2018-05-15 16:00'),
        check_out=str_to_tz_dt('2018-05-16 11:00'))
    get_test_booking(True, reservation=reservation)
    get_test_rental_checklist(True, rental=reservation.rental)
    api = Mock(spec=API)
    create_response = copy.deepcopy(CREATE_JOB)
    create_response['jobRequest.create'][0]['jobRequestId'] = 'first_id'
    api.job_request_create.return_value = FakeResponse(True, create_response)
    api.job_request_cancel.return_value = FakeResponse(True, CANCEL_JOB)

    cleaning = Cleaning.objects.create_job_request(reservation, api)
    self.assertIsNotNone(Cleaning.objects.filter(pk=cleaning.pk).first())
    self.assertEqual(
        1, Cleaning.objects.filter(reservation=reservation).count())
    self.assertEqual(
        str_to_tz_dt('2018-05-16 11:15'), cleaning.offered_start_time)

    reservation.check_out = str_to_tz_dt('2018-05-17 11:00')
    reservation.save()
    create_response['jobRequest.create'][0]['jobRequestId'] = 'second_id'
    post_sync.send(sender=Reservation, instance=reservation, api=api)

    self.assertEqual(
        [call('first_id')], api.job_request_cancel.call_args_list)
    self.assertIsNone(Cleaning.objects.filter(pk=cleaning.pk).first())
    self.assertEqual(
        1, Cleaning.objects.filter(reservation=reservation).count())
    cleaning_2 = Cleaning.objects.get(reservation=reservation)
    self.assertEqual('second_id', cleaning_2.job_request_id)
    self.assertEqual(
        str_to_tz_dt('2018-05-17 11:15'), cleaning_2.offered_start_time)

  def test_reservation_canceled(self):
    reservation = get_test_reservation(
        True, check_in=str_to_tz_dt('2018-05-15 16:00'),
        check_out=str_to_tz_dt('2018-05-16 11:00'))
    get_test_rental_checklist(True, rental=reservation.rental)
    api = Mock(spec=API)
    create_response = copy.deepcopy(CREATE_JOB)
    create_response['jobRequest.create'][0]['jobRequestId'] = 'first_id'
    api.job_request_create.return_value = FakeResponse(True, create_response)
    api.job_request_cancel.return_value = FakeResponse(True, CANCEL_JOB)

    get_test_booking(True, reservation=reservation)

    Cleaning.objects.create_job_request(reservation, api)

    reservation.status = CANCELED
    reservation.save()
    post_sync.send(sender=Reservation, instance=reservation, api=api)

    self.assertEqual(
        [call('first_id')], api.job_request_cancel.call_args_list)
    self.assertEqual(
        0, Cleaning.objects.filter(reservation=reservation).count())


class APITests(TestCase):
  def test_response_is_ok(self):
    api = API()
    self.assertFalse(api.response_data_is_ok(ERROR_RESPONSE))
    self.assertTrue(api.response_data_is_ok(CREATE_JOB))
    self.assertTrue(api.response_data_is_ok(SET_SOURCE_PROPERTY_ID_RESPONSE))


class RentalChecklistTests(TestCase):
  def test_set_source_property_id(self):
    # cleaning.py has a post save signal that kicks off a background task to
    # set the source_property_id when a rental checklist gets saved with a
    # properly_rental_id but no source_property_id. I can't work out how to get
    # my mock in there.
    try:
      get_test_rental_checklist(
          True, properly_rental_id='goatsandboats', source_property_id=None)
    except CantUseTheNet:
      pass
    rc = RentalChecklist.objects.first()
    api = Mock(spec=API)
    api.property_update.return_value = SET_SOURCE_PROPERTY_ID_RESPONSE
    self.assertEqual('goatsandboats', rc.get_source_property_id(api=api))
    rc.refresh_from_db()
    self.assertEqual(rc.source_property_id, 'goatsandboats')
    expected = {
        'propertyId': 'goatsandboats',
        'changes': {'sourceId': 'goatsandboats'}}
    self.assertEqual([call(expected)], api.property_update.call_args_list)


class MessageTests(TestCase):
  def test_overlapping_job_request_accepted(self):
    bob = get_test_cleaner(
        True, name='Bob Bill', email='bob@bill.boing', phone='543-543-5432')
    check_1 = get_test_rental_checklist(True, full_address='123 Texas St.')
    check_2 = get_test_rental_checklist(True, full_address='321 Paris Av.')
    res_1 = get_test_reservation(
        True, check_in=str_to_tz_dt('2018-05-15 16:00'),
        check_out=str_to_tz_dt('2018-05-16 11:00'), rental=check_1.rental)
    res_2 = get_test_reservation(
        True, check_in=str_to_tz_dt('2018-05-15 16:00'),
        check_out=str_to_tz_dt('2018-05-16 11:00'), rental=check_2.rental)
    get_test_cleaning(
        True, job_request_id='job_1', reservation=res_1, accepted_by=bob)
    get_test_cleaning(
        True, job_request_id='job_2', reservation=res_2)

    hook = copy.deepcopy(ACCEPTED_JOB_WEBHOOK)
    hook['results'][0]['jobRequestId'] = 'job_2'
    hook['results'][0]['serviceProvider'] = 'bob@bill.boing'

    email_sender = Mock(spec=EmailSender)
    message_sender = MessageSender(email_sender=email_sender)
    for i in range(2):
      RawEvent.objects.create(json=json.dumps(hook)).handle(
          message_sender=message_sender)

    content = (
        'cleaner: Bob Bill bob@bill.boing 543-543-5432\n'
        'cleaning time: 2018-05-16 11:15am\n'
        'job 1: 123 Texas St.\n'
        'job 2: 321 Paris Av.\n'
        'alerts sent to: jerseycitystaff@stayd.com')
    expected = [call(
        '1 cleaner, 1 time slot, 2 jobs', content, 'heroku@stayd.com',
        ['jerseycitystaff@stayd.com'])]
    self.assertEqual(expected, email_sender.send_mail.call_args_list)

  def test_send_9am_daily_job_reminders(self):
    cleaner = get_test_cleaner(True, phone='555-444-3210')
    get_test_subject_line(
        True, reason=GOOD_MORNING_TODAYS_JOBS, subject='Hey cleanings!')
    today = date.today()
    get_test_cleaning(
        True, accepted_by=cleaner, reservation=get_test_reservation(
            True, full_address='123 Buckingham, New York',
            check_out=make_aware(datetime(
                today.year, today.month, today.day, 11))))

    front = Mock(spec=Front)
    front.send_sms.return_value = FakeSendSMSResult()
    message_sender = MessageSender(front=front)
    for i in range(2):
      Message.objects.send_9am_daily_job_reminders(
          message_sender=message_sender)

    content = 'Hey cleanings! 123 Buckingham, New York 11:15am'
    self.assertEqual(
        [call('555-444-3210', content)], front.send_sms.call_args_list)
    self.assertEqual(
        1, Message.objects.filter(reason=GOOD_MORNING_TODAYS_JOBS).count())

  def test_send_10_minute_late_cleaning_notifications(self):
    cleaner = get_test_cleaner(True, phone='555-444-3210')

    get_test_cleaning(
        True, accepted_by=cleaner, reservation=get_test_reservation(
            True, full_address='123 Buckingham, New York',
            check_in=str_to_tz_dt('2018-04-01 16:00'),
            check_out=str_to_tz_dt('2018-05-01 11:00')))
    get_test_cleaning(  # Slightly too late
        True, accepted_by=get_test_cleaner(True),
        reservation=get_test_reservation(
            True, full_address='A different place, New York',
            check_in=str_to_tz_dt('2018-04-01 16:00'),
            check_out=str_to_tz_dt('2018-05-01 11:30')))

    front = Mock(spec=Front)
    front.send_sms.return_value = FakeSendSMSResult()
    message_sender = MessageSender(front=front)
    for i in range(2):
      Message.objects.send_10_minute_late_cleaning_notifications(
          nnow=str_to_tz_dt('2018-05-01 11:25:01'),
          message_sender=message_sender)

    content = (
        'This cleaning was supposed to start 10 minutes ago: '
        '123 Buckingham, New York 11:15am')
    self.assertEqual(
        [call('555-444-3210', content)], front.send_sms.call_args_list)
    self.assertEqual(
        1, Message.objects.filter(reason=START_10_MINUTES_LATE).count())

  def test_send_15_minute_late_cleaning_notifications(self):
    cleaner = get_test_cleaner(
        True, name='Baron von Clean', phone='555-555-4040',
        email='baron@clean.von')

    get_test_cleaning(
        True, accepted_by=cleaner, reservation=get_test_reservation(
            True, full_address='123 Buckingham, New York',
            alerts_email='buckingham@stayd.com',
            check_in=str_to_tz_dt('2018-04-01 16:00'),
            check_out=str_to_tz_dt('2018-05-01 11:00')))

    email_sender = Mock(spec=EmailSender)
    message_sender = MessageSender(email_sender=email_sender)
    Message.objects.send_15_minute_late_cleaning_notifications(
        nnow=str_to_tz_dt('2018-05-01 11:30:01'),
        message_sender=message_sender)
    subject = (
        'Their cleaning was supposed to start 15 minutes ago')
    content = (
        'Baron von Clean 555-555-4040 baron@clean.von 123 Buckingham, '
        'New York 11:15am')
    expected = [call(
        subject, content, 'heroku@stayd.com',
        ['buckingham@stayd.com'])]
    self.assertEqual(expected, email_sender.send_mail.call_args_list)

  def test_send_cleaning_taking_too_long_notifications(self):
    cleaner = get_test_cleaner(
        True, name='Baron von Clean', phone='555-555-4040',
        email='baron@clean.von')
    get_test_cleaning(
        True, full_address='123 Buckingham, New York',
        alerts_email='buckingham@stayd.com',
        check_in=str_to_tz_dt('2018-04-01 16:00'),
        check_out=str_to_tz_dt('2018-05-01 11:00'),
        accepted_by=cleaner, started_at=str_to_tz_dt('2018-05-01 11:20'))
    email_sender = Mock(spec=EmailSender)
    message_sender = MessageSender(email_sender=email_sender)

    for i in range(2):
      Message.objects.send_cleaning_taking_too_long_notifications(
          nnow=str_to_tz_dt('2018-05-01 14:55'), message_sender=message_sender)

    self.assertEqual(1, len(email_sender.send_mail.call_args_list))
    subject = 'This cleaning is taking too long'
    content = (
        'Baron von Clean 555-555-4040 baron@clean.von 123 Buckingham, '
        'New York\n'
        'Started at: 11:20am\n'
        'Current duration: 3 hours 35 minutes\n'
        'Completed yet: False')
    expected = [call(
        subject, content, 'heroku@stayd.com',
        ['buckingham@stayd.com'])]
    self.assertEqual(expected, email_sender.send_mail.call_args_list)

  def test_send_unclaimed_cleaning_in_lt_48_hours(self):
    cleaning = get_test_cleaning(
        True, accepted_by=None, reservation=get_test_reservation(
            True, full_address='123 Buckingham, New York',
            alerts_email='buckingham@stayd.com',
            check_out=str_to_tz_dt('2018-10-17 11:00')))
    Cleaning.objects.filter(pk=cleaning.pk).update(
        created_at=str_to_tz_dt('2018-10-15 08:00'))

    nnow = str_to_tz_dt('2018-10-15 11:16')
    email_sender = Mock(spec=EmailSender)
    message_sender = MessageSender(email_sender=email_sender)
    for i in range(2):
      Message.objects.send_unclaimed_cleaning_in_lt_48_hours(
          nnow=nnow, message_sender=message_sender)

    subject = 'Unclaimed cleaning in less than 48 hours'
    content = '123 Buckingham, New York 2018-10-17 11:15am'
    expected = [call(
        subject, content, 'heroku@stayd.com',
        ['buckingham@stayd.com'])]
    self.assertEqual(1, len(email_sender.send_mail.call_args_list))
    self.assertEqual(expected, email_sender.send_mail.call_args_list)


class BookingTests(TestCase):
  def test_create_booking(self):
    reservation = get_test_reservation(
        True, channel_reservation_id='dubstepper', first_name='Bob',
        last_name='Slob', full_name='Bob Slob',
        check_in=str_to_tz_dt('2018-05-15 16:00'),
        check_out=str_to_tz_dt('2018-05-16 11:00'), channel_id='GuestBob')
    get_test_rental_checklist(
        True, rental=reservation.rental, source_property_id='hippitydoodah')
    self.assertEqual(
        0, Booking.objects.filter(reservation=reservation).count())
    api = Mock(spec=API)
    api.booking_create.return_value = FakeResponse(True, BOOKING_CREATE)

    post_sync.send(sender=Reservation, instance=reservation, api=api)

    self.assertEqual(
        1, Booking.objects.filter(reservation=reservation).count())
    booking = Booking.objects.get(reservation=reservation)
    self.assertEqual('d8h38hf8h8fh38h83ff3rw', booking.booking_id)
    self.assertEqual(reservation, booking.reservation)
    self.assertEqual('dubstepper', booking.get_source_booking_id())
    expected_data = {
        'sourcePropertyId': 'hippitydoodah',
        'sourceBookingId': 'dubstepper',
        'startDate': '2018-05-15T20:00:00Z',
        'endDate': '2018-05-16T15:00:00Z',
        'title': 'API reservation for Bob Slob',
        'numberOfGuests': 1,
        'guestDetails': [{
            'sourceId': 'GuestBob',
            'firstName': 'Bob',
            'lastName': 'Slob'}]}
    self.assertEqual([call(expected_data)], api.booking_create.call_args_list)
