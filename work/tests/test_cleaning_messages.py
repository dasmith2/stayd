from unittest.mock import Mock, call

from django.conf import settings

from work.models.cleaning_messages import (
    send_unclaimed_cleaning_in_lt_x_hours, send_check_in_soon_notifications,
    send_independent_cleaning_taking_too_long_notifications,
    send_cleaning_unasigned, send_confirmed_no_cleaning,
    send_work_co_not_finished_by_3ish, send_new_cleaning_available)
from work.models.message import (
    Message, UNCLAIMED_CLEANING_IN_LT_48_HOURS, MessageSender,
    CLEAN_CO_CLEANING_NOT_ASSIGNED_2_HOURS_BEFORE,
    CLEAN_CO_CLEANING_NOT_ASSIGNED_3_HOURS_BEFORE,
    CLEAN_CO_CLEANING_NOT_ASSIGNED_18_HOURS_BEFORE,
    CLEAN_CO_CLEANING_NOT_ASSIGNED_24_HOURS_BEFORE,
    CLEAN_CO_CLEANING_NOT_DONE_BY_3_00,
    CLEAN_CO_CLEANING_NOT_DONE_BY_3_10, EMAIL,
    NEW_CLEANING_AVAILABLE, CONFIRMED_NO_CLEANING)
from work.tests.test_cleaning import get_test_cleaning
from work.tests.test_work_co import get_test_work_co
from work.tests.test_work_co_worker import get_test_work_co_worker
from work.tests.test_rental import get_test_properly_rental
from work.tests.test_work import get_test_independent_worker
from rentals.tests import get_test_rental, get_test_building
from reservations.tests import get_test_reservation
from util.email import EmailSender
from util.tests import TestCase
from util.timezone import str_to_tz_dt


class WorkCoMessageTests(TestCase):
  def setUp(self):
    super().setUp()

    self.work_co = get_test_work_co(alerts_email='alert@workco.tom')
    self.cleaner = get_test_work_co_worker(work_co=self.work_co)
    self.building = get_test_building(alerts_email='alert@building.boom')
    self.rental = get_test_rental(nickname='Outdoors', building=self.building)
    get_test_properly_rental(clean_co=self.work_co, rental=self.rental)
    self.reservation = get_test_reservation(
        rental=self.rental, check_in=str_to_tz_dt('2018-12-01 16:00'),
        check_out=str_to_tz_dt('2018-12-02 11:00'))
    self.cleaning = get_test_cleaning(
        reservation=self.reservation, offered_to=[self.cleaner],
        accepted_by=self.cleaner, started_at=None, completed_at=None,
        offered_start_time=str_to_tz_dt('2018-12-02 11:15'),
        created_at=str_to_tz_dt('2018-11-20 12:00'))
    self.message_sender = Mock(spec=MessageSender)

  def test_send_confirmed_no_cleaning(self):
    self.cleaning.delete()
    for i in range(2):
      send_confirmed_no_cleaning(
          nnow=str_to_tz_dt('2018-12-01 11:00'),
          message_sender=self.message_sender)
    message = Message.objects.get(
        to='alert@building.boom', reason=CONFIRMED_NO_CLEANING, kind=EMAIL,
        subject='Cleaning blocked at Outdoors on 2018-12-02', work=None)
    self.assertEqual([call(message)], self.message_sender.send.call_args_list)

  def test_send_new_cleaning_available(self):
    # As this is a new message, make sure it doesn't go crazy and notify for
    # all existing cleanings.
    send_new_cleaning_available(
        nnow=str_to_tz_dt('2018-11-22 12:00'),
        message_sender=self.message_sender)
    self.assertFalse(Message.objects.exists())

    for i in range(2):
      send_new_cleaning_available(
          nnow=str_to_tz_dt('2018-11-20 23:00'),
          message_sender=self.message_sender)

    message = Message.objects.get(
        work=self.cleaning, reason=NEW_CLEANING_AVAILABLE, kind=EMAIL,
        to='alert@workco.tom',
        content='https://clean.hihoward.com/clean_co_cleanings/')
    self.assertEqual([call(message)], self.message_sender.send.call_args_list)

  def test_send_work_co_not_finished_by_3ish(self):
    self.do_test_send_work_co_not_finished_by_3ish()

  def test_send_work_co_not_finished_by_3ish_no_accepted_by(self):
    self.cleaning.accepted_by = None
    self.cleaning.save()
    self.do_test_send_work_co_not_finished_by_3ish()

  def do_test_send_work_co_not_finished_by_3ish(self):
    send_work_co_not_finished_by_3ish(
        nnow=str_to_tz_dt('2018-12-02 14:59'),
        message_sender=self.message_sender)
    self.assertFalse(Message.objects.exists())

    for i in range(2):
      send_work_co_not_finished_by_3ish(
          nnow=str_to_tz_dt('2018-12-02 15:00'),
          message_sender=self.message_sender)
    message_00 = Message.objects.get(
        work=self.cleaning, reason=CLEAN_CO_CLEANING_NOT_DONE_BY_3_00,
        kind=EMAIL, to='alert@workco.tom')
    self.assertEqual(
        [call(message_00)], self.message_sender.send.call_args_list)

    for i in range(2):
      send_work_co_not_finished_by_3ish(
          nnow=str_to_tz_dt('2018-12-02 15:10'),
          message_sender=self.message_sender)
    message_10 = Message.objects.get(
        work=self.cleaning, reason=CLEAN_CO_CLEANING_NOT_DONE_BY_3_10,
        kind=EMAIL, to='alert@building.boom')
    self.assertEqual(
        [call(message_00), call(message_10)],
        self.message_sender.send.call_args_list)

  def test_send_cleaning_unasigned(self):
    send_cleaning_unasigned(
        nnow=str_to_tz_dt('2018-12-02 09:15'),
        message_sender=self.message_sender)
    self.assertFalse(Message.objects.exists())
    self.cleaning.offered_to.set([])
    send_cleaning_unasigned(
        nnow=str_to_tz_dt('2018-12-01 11:14'),
        message_sender=self.message_sender)
    self.assertFalse(Message.objects.exists())

    # Don't alert if it's canceled
    self.cleaning.canceled_at = str_to_tz_dt('2018-12-01 10:00')
    self.cleaning.save()
    send_cleaning_unasigned(
        nnow=str_to_tz_dt('2018-12-01 11:15'),
        message_sender=self.message_sender)
    self.assertEqual(0, len(self.message_sender.send.call_args_list))

    self.cleaning.canceled_at = None
    self.cleaning.save()

    for i in range(2):
      send_cleaning_unasigned(
          nnow=str_to_tz_dt('2018-12-01 11:15'),
          message_sender=self.message_sender)
    alert_24 = Message.objects.get(
        reason=CLEAN_CO_CLEANING_NOT_ASSIGNED_24_HOURS_BEFORE,
        work=self.cleaning, to='alert@workco.tom', kind=EMAIL)
    self.assertEqual([call(alert_24)], self.message_sender.send.call_args_list)

    send_cleaning_unasigned(
        nnow=str_to_tz_dt('2018-12-01 17:15'),
        message_sender=self.message_sender)
    alert_18 = Message.objects.get(
        reason=CLEAN_CO_CLEANING_NOT_ASSIGNED_18_HOURS_BEFORE,
        work=self.cleaning, to='alert@building.boom', kind=EMAIL)
    self.assertEqual(
        [call(alert_24), call(alert_18)],
        self.message_sender.send.call_args_list)

    send_cleaning_unasigned(
        nnow=str_to_tz_dt('2018-12-02 08:15'),
        message_sender=self.message_sender)
    alert_3 = Message.objects.get(
        reason=CLEAN_CO_CLEANING_NOT_ASSIGNED_3_HOURS_BEFORE,
        work=self.cleaning, to='alert@workco.tom', kind=EMAIL)
    self.assertEqual(
        [call(alert_24), call(alert_18), call(alert_3)],
        self.message_sender.send.call_args_list)

    send_cleaning_unasigned(
        nnow=str_to_tz_dt('2018-12-02 09:15'),
        message_sender=self.message_sender)
    alert_2 = Message.objects.get(
        reason=CLEAN_CO_CLEANING_NOT_ASSIGNED_2_HOURS_BEFORE,
        work=self.cleaning, to='alert@building.boom', kind=EMAIL)
    self.assertEqual(4, len(self.message_sender.send.call_args_list))
    self.assertEqual(
        [call(alert_24), call(alert_18), call(alert_3), call(alert_2)],
        self.message_sender.send.call_args_list)


class IndependentCleanerNotificationTests(TestCase):
  def test_send_cleaning_taking_too_long_notifications(self):
    cleaner = get_test_independent_worker(
        name='Baron von Clean', phone='555-555-4040', email='baron@clean.von')
    get_test_cleaning(
        full_address='123 Buckingham, New York', nickname='Buckingham',
        alerts_email='buckingham@stayd.com',
        check_in=str_to_tz_dt('2018-04-01 16:00'),
        check_out=str_to_tz_dt('2018-05-01 11:00'),
        accepted_by=cleaner, started_at=str_to_tz_dt('2018-05-01 11:20'))
    email_sender = Mock(spec=EmailSender)
    message_sender = MessageSender(email_sender=email_sender)

    for i in range(2):
      send_independent_cleaning_taking_too_long_notifications(
          nnow=str_to_tz_dt('2018-05-01 14:55'), message_sender=message_sender)

    self.assertEqual(1, len(email_sender.send_mail.call_args_list))
    (subject, content, from_email, to_emails) = (
        email_sender.send_mail.call_args_list[0][0])
    self.assertEqual(
        'This cleaning is taking too long. 2018-05-01 at Buckingham', subject)
    self.assertTrue(content.find(
        'The cleaning on 2018-05-01 11:15am at 123 Buckingham, New York') >= 0)
    self.assertTrue(content.find(
        'the cleaner Baron von Clean at 555-555-4040 and') >= 0)
    self.assertEqual(settings.SERVER_EMAIL, from_email)
    self.assertEqual(['buckingham@stayd.com'], to_emails)

  def test_send_check_in_soon_notifications(self):
    cleaner = get_test_independent_worker(
        name='Baron von Clean', phone='555-555-4040',
        email='baron@clean.von')
    rental = get_test_rental(
        full_address='123 Buckingham, New York', nickname='Buckingham')
    get_test_cleaning(
        rental=rental,
        alerts_email='buckingham@stayd.com',
        check_in=str_to_tz_dt('2018-04-01 16:00'),
        check_out=str_to_tz_dt('2018-05-01 11:00'),
        accepted_by=cleaner, started_at=str_to_tz_dt('2018-05-01 13:20'))
    get_test_reservation(
        check_in=str_to_tz_dt('2018-05-01 16:00'),
        check_out=str_to_tz_dt('2018-05-02 11:00'), rental=rental)

    email_sender = Mock(spec=EmailSender)
    message_sender = MessageSender(email_sender=email_sender)
    for i in range(2):
      send_check_in_soon_notifications(
          nnow=str_to_tz_dt('2018-05-01 15:36'), message_sender=message_sender)

    self.assertEqual(1, len(email_sender.send_mail.call_args_list))
    (subject, content, from_email, to_emails) = (
        email_sender.send_mail.call_args_list[0][0])
    self.assertEqual((
        'Cleaning not finished: Check-in in 25 minutes. '
        '2018-05-01 at Buckingham'), subject)
    self.assertTrue(content.find('begins at 4pm') >= 0)
    self.assertTrue(content.find('Worker name: Baron von Clean') >= 0)
    self.assertTrue(content.find('Worker phone number: 555-555-4040') >= 0)
    self.assertTrue(content.find('Address: 123 Buckingham, New York') >= 0)

  def test_send_unclaimed_cleaning_in_lt_48_hours(self):
    properly_rental = get_test_properly_rental(
        full_address='123 Buckingham, New York',
        nickname='Buckingham',
        alerts_email='buckingham@stayd.com')
    get_test_cleaning(  # Should alert.
        accepted_by=None, created_at=str_to_tz_dt('2018-10-15 08:00'),
        reservation=get_test_reservation(
            rental=properly_rental.rental,
            check_out=str_to_tz_dt('2018-10-17 11:00')))
    clean_co_rental = get_test_properly_rental(
        clean_co=get_test_work_co()).rental
    get_test_cleaning(  # Clean co cleaning shouldn't alert.
        accepted_by=None, created_at=str_to_tz_dt('2018-10-15 08:00'),
        reservation=get_test_reservation(
            rental=clean_co_rental,
            check_out=str_to_tz_dt('2018-10-17 11:00')))

    nnow = str_to_tz_dt('2018-10-15 11:16')
    email_sender = Mock(spec=EmailSender)
    message_sender = MessageSender(email_sender=email_sender)
    for i in range(2):
      send_unclaimed_cleaning_in_lt_x_hours(
          start_within_hours=48, reason=UNCLAIMED_CLEANING_IN_LT_48_HOURS,
          nnow=nnow, message_sender=message_sender)

    # Reinstate after removing dave@hihoward.com from
    # send_unclaimed_cleaning_in_lt_x_hours self.assertEqual(1,
    # len(email_sender.send_mail.call_args_list))
    (subject, content, from_email, to_emails) = (
        email_sender.send_mail.call_args_list[0][0])

    self.assertEqual(
        'Unclaimed cleaning in less than 48 hours. 2018-10-17 at Buckingham',
        subject)
    self.assertTrue(content.find('Date of cleaning: 2018-10-17 11:15am') >= 0)
    self.assertTrue(content.find('Address: 123 Buckingham, New York') >= 0)
    self.assertEqual(settings.SERVER_EMAIL, from_email)
    self.assertEqual(['buckingham@stayd.com'], to_emails)
