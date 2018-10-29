from datetime import timedelta, date, datetime
from dateutil.parser import parse
from decimal import Decimal
from unittest.mock import Mock, call

from django.utils.timezone import now, make_aware
from djmoney.money import Money

from front.models import Front, FakeSendSMSResult
from properly.api import API
from properly.api_examples import (
    ERROR_RESPONSE, CREATE_JOB, SET_SOURCE_PROPERTY_ID_RESPONSE)
from properly.models.cleaning import (
    Cleaner, Cleaning, RentalChecklist, Checklist, HoursAndPayRow)
from properly.models.message_sender import MessageSender
from properly.models.messages import (
    SubjectLine, Message,
    send_9am_daily_job_reminders_background,
    send_10_minute_late_cleaning_notifications_background,
    send_15_minute_late_cleaning_notifications_background,
    send_unclaimed_cleaning_in_lt_48_hours_background,
    UNCLAIMED_CLEANING_IN_LT_48_HOURS, GOOD_MORNING_TODAYS_JOBS,
    START_10_MINUTES_LATE)
from rentals.tests import get_test_rental, get_test_building
from reservations.tests import get_test_reservation
from util.email import EmailSender
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


def get_test_subject_line(create, **kwargs):
  subject_line = SubjectLine(
      reason=kwargs.get('reason', UNCLAIMED_CLEANING_IN_LT_48_HOURS),
      subject=kwargs.get('subject', 'Warning: unclaimed cleaning'))
  if create:
    subject_line.save()
  return subject_line


class CleaningTests(TestCase):
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
    get_test_reservation(
        True, check_out=parse('2018-10-28T15:00:00.000Z'),
        channel_reservation_id='ibelieveinafingcalledlove',
        rental=rental, id_verified=True, balance_due=Money('0.0', 'USD'))
    api = Mock(spec=API)
    api.job_request_create.return_value = FakeResponse(True, CREATE_JOB)

    cleanings = Cleaning.objects.create_job_requests(
        api=api, nnow=str_to_tz_dt('2018-10-27 12:00'))

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


class MessageTests(TestCase):
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
      send_9am_daily_job_reminders_background(message_sender=message_sender)

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
      send_10_minute_late_cleaning_notifications_background(
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
    send_15_minute_late_cleaning_notifications_background(
        nnow=str_to_tz_dt('2018-05-01 11:30:01'),
        message_sender=message_sender)
    subject = (
        'Their cleaning was supposed to start 15 minutes ago: 2018-05-01')
    content = (
        'Baron von Clean 555-555-4040 baron@clean.von 123 Buckingham, '
        'New York 11:15am')
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
      send_unclaimed_cleaning_in_lt_48_hours_background(
          nnow=nnow, message_sender=message_sender)

    subject = 'Unclaimed cleaning in less than 48 hours 2018-10-17 11:15am'
    content = '123 Buckingham, New York 2018-10-17 11:15am'
    expected = [call(
        subject, content, 'heroku@stayd.com',
        ['buckingham@stayd.com'])]
    self.assertEqual(1, len(email_sender.send_mail.call_args_list))
    self.assertEqual(expected, email_sender.send_mail.call_args_list)
