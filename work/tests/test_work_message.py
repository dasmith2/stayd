import json
from unittest.mock import Mock, call

from django.conf import settings

from front.models import Front, DeliveryErrorChecker, FakeSendSMSResult
from rentals.tests import (
    get_test_sms_channel, get_test_rental, get_test_building)
from reservations.tests import get_test_reservation
from util.email import EmailSender
from util.tests import TestCase
from util.timezone import str_to_tz_dt
from work.api_examples import ACCEPTED_JOB_WEBHOOK
from work.models.fixed_or_flexible import FIXED, FLEXIBLE
from work.models.maintenance import Maintenance
from work.models.message import (
    Message, MessageSender, SubjectLine, EMAIL, SMS,
    ONE_WORKER_1_TIME_SLOT_2_JOBS, GOOD_MORNING_TODAYS_JOBS,
    GOOD_MORNING_2ND_SMS, START_10_MINUTES_LATE, START_15_MINUTES_LATE,
    START_20_MINUTES_LATE, SKEPTICAL_CAN_FINISH_FLEXIBLE_ON_TIME,
    NOT_STARTED_1_HOUR_AFTER_SHOULD_BE_DONE, JOB_ON_PROPERLY_AND_KEYS)
from work.models.raw_event import RawEvent
from work.models.work_message import (
    send_9am_daily_job_reminders, alert_overlap_accepted,
    send_delayed_work_start_messages, send_cant_complete_flexible_in_time,
    send_not_started_an_hour_after_supposed_to_be_done,
    resend_server_error_messages)
from work.tests.test_cleaning import (
    get_test_cleaning_config, get_test_cleaning)
from work.tests.test_maintenance import get_test_maintenance
from work.tests.test_message import get_test_subject_line, get_test_message
from work.tests.test_one_off import get_test_one_off
from work.tests.test_rental import get_test_properly_rental
from work.tests.test_work import get_test_independent_worker
from work.tests.test_work_co import get_test_work_co
from work.tests.test_work_co_worker import get_test_work_co_worker
from util.html_status_codes import ServerError
from util.signals import post_sync


class ActionTests(TestCase):
  def test_action_on_keys_and_properly_alerts(self):
    maintenance = get_test_maintenance(
        offered_start_time=str_to_tz_dt('2018-12-24 11:15'),
        action_on_properly=True, action_on_keys=True)
    message_sender = Mock(spec=MessageSender)
    for i in range(2):
      post_sync.send(
          sender=Maintenance, instance=maintenance,
          message_sender=message_sender)
    message = Message.objects.get(
        reason=JOB_ON_PROPERLY_AND_KEYS, work=maintenance)
    self.assertEqual([call(message)], message_sender.send.call_args_list)


class ResendServerErrorMessageTests(TestCase):
  def test_resend_server_error_messages(self):
    front = Mock(spec=Front)
    front.send_sms.side_effect = ServerError('Wah!')
    message_sender = MessageSender(
        front=front, delivery_error_checker=DeliveryErrorChecker())
    work = get_test_one_off(
        offered_start_time=str_to_tz_dt('2018-12-25 11:55'),
        sms_staff_from=get_test_sms_channel(identifier='whatever'))
    message = get_test_message(
        to='666-666-6666', kind=SMS, work=work,
        content='How will I know when Im ready?',
        when=str_to_tz_dt('2018-12-25 11:55'))

    message_sender.send(message)
    message.refresh_from_db()
    self.assertEqual(1, len(front.send_sms.call_args_list))

    self.assertEqual(1, message.server_error_count)
    self.assertTrue(message.please_resend_due_to_server_error)

    front.send_sms.side_effect = None
    front.send_sms.return_value = FakeSendSMSResult()
    resend_server_error_messages(
        message_sender=message_sender, nnow=str_to_tz_dt('2018-12-25 12:00'))
    message.refresh_from_db()

    self.assertEqual(2, len(front.send_sms.call_args_list))
    self.assertEqual(1, message.server_error_count)
    self.assertFalse(message.please_resend_due_to_server_error)

    resend_server_error_messages(
        message_sender=message_sender, nnow=str_to_tz_dt('2018-12-25 12:05'))
    self.assertEqual(2, len(front.send_sms.call_args_list))


class WorkCoLateStartTests(TestCase):
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
        offered_start_time=str_to_tz_dt('2018-12-02 11:15'))
    self.message_sender = Mock(spec=MessageSender)

  def test_send_late_not_offered(self):
    self.cleaning.accepted_by = None
    self.cleaning.offered_to.set([])
    self.cleaning.save()
    self.test_send_late_start_work_co_notifications()

  def test_send_late_start_not_accepted(self):
    self.cleaning.accepted_by = None
    self.cleaning.save()
    self.test_send_late_start_work_co_notifications()

  def test_send_late_start_work_co_notifications(self):
    for i in range(2):
      send_delayed_work_start_messages(
          nnow=str_to_tz_dt('2018-12-02 11:25:01'),
          message_sender=self.message_sender)
    ten_late = Message.objects.get(
        reason=START_10_MINUTES_LATE, work=self.cleaning,
        to='alert@workco.tom', reply_to='alert@building.boom', kind=EMAIL)
    self.assertEqual([call(ten_late)], self.message_sender.send.call_args_list)
    for i in range(2):
      send_delayed_work_start_messages(
          nnow=str_to_tz_dt('2018-12-02 11:35:01'),
          message_sender=self.message_sender)
    twenty_late = Message.objects.get(
        reason=START_20_MINUTES_LATE, work=self.cleaning,
        to='alert@building.boom', kind=EMAIL)
    self.assertEqual(
        [call(ten_late), call(twenty_late)],
        self.message_sender.send.call_args_list)


class IndependentCleanerLateStartTests(TestCase):
  def test_send_10_minute_late_cleaning_notifications(self):
    cleaner = get_test_independent_worker(
        phone='555-444-3210', name='Bob Slob')
    sms_channel = get_test_sms_channel(identifier='sms_blah')
    building = get_test_building(
        alerts_email='alert@building.boom', sms_staff_from=sms_channel)

    rental_1 = get_test_rental(nickname='Outdoors 1', building=building)
    get_test_properly_rental(rental=rental_1)
    get_test_cleaning(  # Started on time but a while ago
        accepted_by=get_test_independent_worker(),
        started_at=str_to_tz_dt('2018-05-01 10:20'),
        reservation=get_test_reservation(
            rental=rental_1,
            check_in=str_to_tz_dt('2018-04-01 16:00'),
            check_out=str_to_tz_dt('2018-05-01 10:00')))
    rental_2 = get_test_rental(nickname='Outdoors 2', building=building)
    get_test_properly_rental(rental=rental_2)
    get_test_cleaning(  # Started ahead of schedule! Should be fine.
        accepted_by=get_test_independent_worker(),
        started_at=str_to_tz_dt('2018-05-01 10:04'),
        reservation=get_test_reservation(
            full_address='Disney World, New York',
            check_in=str_to_tz_dt('2018-04-01 16:00'),
            check_out=str_to_tz_dt('2018-05-01 10:00')))
    rental_3 = get_test_rental(nickname='Outdoors 3', building=building)
    get_test_properly_rental(rental=rental_3)
    get_test_cleaning(  # Not started yet. Should cause an alert.
        accepted_by=cleaner,
        started_at=None, reservation=get_test_reservation(
            rental=rental_3,
            check_in=str_to_tz_dt('2018-04-01 16:00'),
            check_out=str_to_tz_dt('2018-05-01 11:00')))
    # Not started yet, but it wasn't even accepted until late.
    rental_4 = get_test_rental(nickname='Outdoors 4', building=building)
    get_test_properly_rental(rental=rental_4)
    get_test_cleaning(
        accepted_by=cleaner, accepted_at=str_to_tz_dt('2018-05-01 11:30'),
        started_at=None, reservation=get_test_reservation(
            rental=rental_4,
            check_in=str_to_tz_dt('2018-04-01 16:00'),
            check_out=str_to_tz_dt('2018-05-01 11:00')))
    rental_5 = get_test_rental(nickname='Outdoors 5', building=building)
    get_test_properly_rental(rental=rental_5)
    get_test_cleaning(  # Canceled.
        accepted_by=cleaner, canceled_at=str_to_tz_dt('2018-05-01 08:00'),
        started_at=None, reservation=get_test_reservation(
            rental=rental_5,
            check_in=str_to_tz_dt('2018-04-01 16:00'),
            check_out=str_to_tz_dt('2018-05-01 11:00')))
    rental_6 = get_test_rental(nickname='Outdoors 6', building=building)
    get_test_properly_rental(rental=rental_6)
    get_test_cleaning(  # Not started yet, but also not late yet.
        accepted_by=get_test_independent_worker(),
        started_at=None, reservation=get_test_reservation(
            rental=rental_6,
            check_in=str_to_tz_dt('2018-04-01 16:00'),
            check_out=str_to_tz_dt('2018-05-01 11:30')))

    front = Mock(spec=Front)
    front.send_sms.return_value = FakeSendSMSResult()
    message_sender = MessageSender(
        front=front, delivery_error_checker=DeliveryErrorChecker())
    for i in range(2):
      send_delayed_work_start_messages(
          nnow=str_to_tz_dt('2018-05-01 11:25:01'),
          message_sender=message_sender)

    self.assertEqual(
        1, Message.objects.filter(reason=START_10_MINUTES_LATE).count())
    self.assertEqual(1, len(front.send_sms.call_args_list))
    (number, content, sms_channel_id) = front.send_sms.call_args_list[0][0]
    self.assertEqual('555-444-3210', number)
    self.assertEqual('sms_blah', sms_channel_id)
    self.assertTrue(content.find('Hi Bob Slob.') >= 0)

  def test_send_15_minute_late_cleaning_notifications(self):
    cleaner = get_test_independent_worker(
        name='Baron von Clean', phone='555-555-4040',
        email='baron@clean.von')

    building = get_test_building(alerts_email='buckingham@stayd.com')
    rental = get_test_rental(
        building=building, full_address='123 Buckingham, New York',
        nickname='Buckingham')
    get_test_properly_rental(rental=rental)
    cleaning = get_test_cleaning(
        accepted_by=cleaner, reservation=get_test_reservation(
            rental=rental, check_in=str_to_tz_dt('2018-04-01 16:00'),
            check_out=str_to_tz_dt('2018-05-01 11:00')))
    Message.objects.create(
        reason=START_10_MINUTES_LATE, work=cleaning,
        when=str_to_tz_dt('2018-05-01 11:25'))

    email_sender = Mock(spec=EmailSender)
    message_sender = MessageSender(email_sender=email_sender)
    for i in range(2):
      send_delayed_work_start_messages(
          nnow=str_to_tz_dt('2018-05-01 11:30:01'),
          message_sender=message_sender)

    Message.objects.get(reason=START_15_MINUTES_LATE, work=cleaning)
    self.assertEqual(1, len(email_sender.send_mail.call_args_list))
    (subject, content, from_email, to_emails) = (
        email_sender.send_mail.call_args_list[0][0])
    expected_subject = (
        'Their cleaning was supposed to start 15 minutes ago. '
        '2018-05-01 at Buckingham')
    self.assertEqual(expected_subject, subject)
    self.assertTrue(content.find('at 123 Buckingham, New York 11:15am') >= 0)
    self.assertTrue(content.find('Worker name: Baron von Clean') >= 0)
    self.assertTrue(content.find('Worker phone number: 555-555-4040') >= 0)
    self.assertEqual(settings.SERVER_EMAIL, from_email)
    self.assertEqual(['buckingham@stayd.com'], to_emails)


class CompleteFlexibleInTimeTests(TestCase):
  def test_send_cant_complete_flexible_in_time(self):
    one_off = get_test_one_off(
        offered_start_time=str_to_tz_dt('2018-12-25 12:00'),
        end_time=str_to_tz_dt('2018-12-25 19:00'),
        expected_duration=2, accepted_by=get_test_independent_worker(),
        alerts_email='building@alert.com', fixed_or_flexible=FLEXIBLE)
    message_sender = Mock(spec=MessageSender)

    send_cant_complete_flexible_in_time(
        nnow=str_to_tz_dt('2018-12-25 17:00'), message_sender=message_sender)
    self.assertEqual(0, Message.objects.count())

    for i in range(2):
      send_cant_complete_flexible_in_time(
          nnow=str_to_tz_dt('2018-12-25 17:15'), message_sender=message_sender)
    message = Message.objects.get(
        to='building@alert.com', reason=SKEPTICAL_CAN_FINISH_FLEXIBLE_ON_TIME,
        kind=EMAIL, subject=SKEPTICAL_CAN_FINISH_FLEXIBLE_ON_TIME,
        work=one_off)
    self.assertEqual([call(message)], message_sender.send.call_args_list)


class NotStartedAnHourAfterSupposedToBeDoneTests(TestCase):
  def test_send_not_started_an_hour_after_supposed_to_be_done(self):
    properly_rental = get_test_properly_rental(
        alerts_email='building@alert.com')
    worker = get_test_independent_worker()

    fixed = get_test_one_off(  # Should be done by 18:00, o/w notify at 19
        offered_start_time=str_to_tz_dt('2018-12-25 16:00'),
        expected_duration=2, accepted_by=worker, fixed_or_flexible=FIXED,
        properly_rental=properly_rental)
    flexible = get_test_one_off(  # Should be done by 19:00, o/w notify at 20
        offered_start_time=str_to_tz_dt('2018-12-25 12:00'),
        end_time=str_to_tz_dt('2018-12-25 19:00'),
        expected_duration=2, accepted_by=worker, fixed_or_flexible=FLEXIBLE,
        properly_rental=properly_rental)

    message_sender = Mock(spec=MessageSender)

    send_not_started_an_hour_after_supposed_to_be_done(
        message_sender=message_sender, nnow=str_to_tz_dt('2018-12-25 18:00'))
    self.assertFalse(Message.objects.exists())

    send_not_started_an_hour_after_supposed_to_be_done(
        message_sender=message_sender, nnow=str_to_tz_dt('2018-12-25 19:00'))
    fixed_message = Message.objects.get(
        work=fixed, reason=NOT_STARTED_1_HOUR_AFTER_SHOULD_BE_DONE)
    self.assertEqual([call(fixed_message)], message_sender.send.call_args_list)

    send_not_started_an_hour_after_supposed_to_be_done(
        message_sender=message_sender, nnow=str_to_tz_dt('2018-12-25 20:00'))
    flexible_message = Message.objects.get(
        work=flexible, reason=NOT_STARTED_1_HOUR_AFTER_SHOULD_BE_DONE)
    self.assertEqual(
        [call(fixed_message), call(flexible_message)],
        message_sender.send.call_args_list)


class Send9AMDailyJobReminderTests(TestCase):
  def setUp(self):
    super().setUp()
    worker = get_test_independent_worker(phone='555-444-3210')
    get_test_subject_line(
        reason=GOOD_MORNING_TODAYS_JOBS, subject='Hey cleanings!')
    sms_channel = get_test_sms_channel(identifier='sms_blah')
    rental = get_test_rental(full_address='The Old Idiot, New York, NY')
    get_test_properly_rental(rental=rental)
    get_test_cleaning(
        accepted_by=worker, reservation=get_test_reservation(
            sms_staff_from=sms_channel,
            check_in=str_to_tz_dt('2018-12-01 16:00'),
            check_out=str_to_tz_dt('2018-12-02 11:00'),
            rental=rental))

    self.message_sender = Mock(spec=MessageSender)

  def test_send_9am_daily_job_reminders(self):
    for i in range(3):
      send_9am_daily_job_reminders(
          message_sender=self.message_sender,
          nnow=str_to_tz_dt('2018-12-02 9:00'))

    message = Message.objects.get(
        reason=GOOD_MORNING_TODAYS_JOBS, kind=SMS, to='555-444-3210')
    self.assertEqual(
        [call(message)], self.message_sender.send.call_args_list)
    self.assertEqual(
        'Hey cleanings!\nCleaning The Old Idiot, New York, NY 11:15am',
        message.content)

  def test_good_morning_2nd_sms(self):
    SubjectLine.objects.create(
        reason=GOOD_MORNING_2ND_SMS,
        subject='Is there something weird with my face?')
    send_9am_daily_job_reminders(
        message_sender=self.message_sender,
        nnow=str_to_tz_dt('2018-12-02 9:00'))
    message = Message.objects.get(
        reason=GOOD_MORNING_2ND_SMS, kind=SMS, to='555-444-3210',
        content='Is there something weird with my face?')
    self.assertEqual(call(message), self.message_sender.send.call_args_list[1])


class MessageTests(TestCase):
  def test_alert_overlap_oneoff_and_cleaning(self):
    bob = get_test_independent_worker()
    cleaning = get_test_one_off(
        alerts_email='alert@alert.alert',
        offered_start_time=str_to_tz_dt('2018-12-15 12:00'), accepted_by=bob)
    one_off = get_test_one_off(
        alerts_email='alert@alert.alert',
        offered_start_time=str_to_tz_dt('2018-12-15 12:00'), accepted_by=bob)
    email_sender = Mock(spec=EmailSender)
    message_sender = MessageSender(email_sender=email_sender)
    alert_overlap_accepted([cleaning, one_off], message_sender)
    Message.objects.get(reason=ONE_WORKER_1_TIME_SLOT_2_JOBS)

  def test_overlapping_job_request_accepted(self):
    bob = get_test_independent_worker(
        name='Bob Bill', email='nikolagirl@yahoo.com', phone='543-543-5432',
        worker_id='boopbapbip')
    check_1 = get_test_cleaning_config(
        full_address='123 Texas St.',
        alerts_email='buckingham@stayd.com')
    check_2 = get_test_cleaning_config(
        full_address='321 Paris Av.', nickname='Buckingham',
        alerts_email='barkingsteak@stayd.com')
    res_1 = get_test_reservation(
        check_in=str_to_tz_dt('2018-05-15 16:00'),
        check_out=str_to_tz_dt('2018-05-16 11:00'),
        rental=check_1.properly_rental.rental)
    res_2 = get_test_reservation(
        check_in=str_to_tz_dt('2018-05-15 16:00'),
        check_out=str_to_tz_dt('2018-05-16 11:00'),
        rental=check_2.properly_rental.rental)
    get_test_cleaning(
        job_request_id='job_1', reservation=res_1, accepted_by=bob)
    get_test_cleaning(
        job_request_id='5cffe19414b48ac5b66f1fce', reservation=res_2)

    email_sender = Mock(spec=EmailSender)
    message_sender = MessageSender(email_sender=email_sender)
    for i in range(2):
      RawEvent.objects.create(json=json.dumps(ACCEPTED_JOB_WEBHOOK)).handle(
          message_sender=message_sender)

    self.assertEqual(1, len(email_sender.send_mail.call_args_list))
    (subject, content, from_email, to_emails) = (
        email_sender.send_mail.call_args_list[0][0])
    self.assertEqual(
        '1 worker, 1 time slot, 2 jobs. 2018-05-16 at Buckingham', subject)
    self.assertTrue(content.find(
        'Worker: Bob Bill nikolagirl@yahoo.com 543-543-5432') >= 0)
    self.assertTrue(content.find('Time: 2018-05-16 11:15am') >= 0)
    self.assertTrue(content.find('123 Texas St.\n321 Paris Av.') >= 0)
    self.assertEqual(settings.SERVER_EMAIL, from_email)
    self.assertEqual(
        ['barkingsteak@stayd.com', 'buckingham@stayd.com'], to_emails)
