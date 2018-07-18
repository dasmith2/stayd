from datetime import datetime, timedelta, time
from unittest.mock import Mock, call

from util.tests import TestCase
from django.conf import settings
from django.utils.dateparse import parse_datetime
from django.utils.timezone import make_aware, now
from djmoney.money import Money

from errors.models import ErrorLogger
from guest_messages.models import (
    Template, Message, DAYS, HOURS, BEFORE, AFTER, CHECKIN, CHECKOUT, BOOKING,
    ID_VERIFICATION_REQUIRED, PAYMENT_DEPOSIT_ID_RECEIVED,
    MORNING_AFTER_ARRIVAL, ReservationSyncer)
from guesty.models import GuestyReservation
from reservations.models import Reservation
from reservations.tests import get_test_reservation
from util.channels import AIRBNB, BOOKINGCOM, HOMEAWAY
from util.clock import Clock
from front.models import Front, FakeSendSMSResult
from util.timezone import str_to_tz_dt


def get_test_template(create, **kwargs):
  template = Template(
      guesty_custom_field_id=kwargs.get('guesty_custom_field_id', 'foo'),
      special_purpose=kwargs.get('special_purpose', ''),
      offset=kwargs.get('offset', 1),
      days_or_hours=kwargs.get('days_or_hours', DAYS),
      before_or_after=kwargs.get('before_or_after', BEFORE),
      triggering_event=kwargs.get('triggering_event', CHECKIN),
      at_time=kwargs.get('at_time', None),
      message=kwargs.get('message', 'Here\'s your message!'),
      pre_scheduled=kwargs.get('pre_scheduled', True))
  if create:
    template.save()
  return template


def get_test_message(create, **kwargs):
  reservation = get_test_reservation(create, **kwargs)

  send_results = (
      "{'conversation_reference': "
      "'0013425ed607a418e4866e16be52612a@frontapp.com', 'message_uid': "
      "'0013425ed607a418e4866e16be52612a', 'status': 'accepted'}")

  message = Message(
      reservation=kwargs.get('reservation', reservation),
      guesty_custom_field_id=kwargs.get('guesty_custom_field_id', 'whatever'),
      special_purpose=kwargs.get('special_purpose', None),
      when_should=kwargs.get('when_should', now() - timedelta(hours=1)),
      when_did=kwargs.get('when_did', now() - timedelta(hours=1)),
      green_light=kwargs.get('green_light', True),
      message=kwargs.get('message', 'Hello world'),
      why_did_not_send=kwargs.get('why_did_not_send', ''),
      sent_to_phone=kwargs.get('sent_to_phone', '555-555-5555'),
      send_results=kwargs.get('send_results', send_results),
      delivery_check_on=kwargs.get('delivery_check_on', None),
      delivery_error=kwargs.get('delivery_error', None))
  if create:
    message.save()
  return message


class TemplateTests(TestCase):
  def test_when_should_offset_only_no_specific_time(self):
    r = get_test_reservation(
        False, booked_at=make_aware(datetime(2018, 3, 2, 13)),
        check_in=make_aware(datetime(2018, 3, 7, 15)),
        check_out=make_aware(datetime(2018, 3, 9, 11)))
    t = get_test_template(False)

    t.offset = 2
    t.days_or_hours = DAYS
    t.before_or_after = BEFORE
    t.triggering_event = CHECKIN
    self.assertEqual(
        make_aware(datetime(2018, 3, 5, 15)),
        t.when_should(r))

    t.offset = 3
    t.days_or_hours = HOURS
    t.before_or_after = AFTER
    t.triggering_event = CHECKOUT
    self.assertEqual(
        make_aware(datetime(2018, 3, 9, 14)),
        t.when_should(r))

    t.triggering_event = BOOKING
    self.assertEqual(
        make_aware(datetime(2018, 3, 2, 16)),
        t.when_should(r))

  def test_when_should_9am_timezone(self):
    check_in = str_to_tz_dt('2018-03-01 17:00:00', 'US/Hawaii')
    check_out = str_to_tz_dt('2018-03-02 11:00:00', 'US/Hawaii')
    r = get_test_reservation(
        True, time_zone='US/Hawaii', check_in=check_in, check_out=check_out)
    # At this point, r.check_in still has a Hawaii timezone.
    # Load the reservation from the database because django stores and
    # retrieves datetimes in UTC. That's where this get tricky.
    r_loaded = Reservation.objects.get(pk=r.pk)

    t = get_test_template(False)
    t.offset = 0
    t.days_or_hours = DAYS
    t.before_or_after = AFTER
    t.triggering_event = CHECKOUT
    t.at_time = time(9)
    self.assertEqual(
        str_to_tz_dt('2018-03-02 09:00:00', 'US/Hawaii'),
        t.when_should(r_loaded))

  def test_message_for_reservation(self):
    r = get_test_reservation(
        True, channel=AIRBNB, airbnb_address_scrape='43 Spud Dr., Idaho',
        city='Austin', first_name='Jill', email='jill@gmail.com')
    r = Reservation.objects.get(pk=r.pk)
    t = get_test_template(False)
    t.message = (
        'Hello {guest_first_name}!{delay}Your reservation is at {address}. '
        'I see you love {Airbnb}A1rbnb{/}{Booking.com}B00king.com{/}'
        '{Homeaway}Home@way{/}.')
    expected = (
        'Hello Jill!{delay}Your reservation is at 43 Spud Dr., Idaho. '
        'I see you love A1rbnb.')
    self.assertEqual(expected, t.message_for_reservation(r))

    r.listing.channel = BOOKINGCOM
    expected = (
        'Hello Jill!{delay}Your reservation is at 43 Spud Dr., Idaho. '
        'I see you love B00king.com.')
    self.assertEqual(expected, t.message_for_reservation(r))

    r.listing.channel = HOMEAWAY
    expected = (
        'Hello Jill!{delay}Your reservation is at 43 Spud Dr., Idaho. '
        'I see you love Home@way.')
    self.assertEqual(expected, t.message_for_reservation(r))

    t.message = 'See {guest_email} re your stay in {city}'
    expected = 'See jill@gmail.com re your stay in Austin'
    self.assertEqual(expected, t.message_for_reservation(r))

    r.listing.channel = AIRBNB
    t.message = '{id_verify_link}'
    expected = 'https://stayd.typeform.com/to/B3BcbH'
    self.assertEqual(expected, t.message_for_reservation(r))

    r.listing.channel = BOOKINGCOM
    t.message = '{id_verify_link} {channel} {checkout_time}'
    expected = 'https://stayd.typeform.com/to/Y3Fpua Booking.com 10 am'
    self.assertEqual(expected, t.message_for_reservation(r))

  def test_create_for_reservation(self):
    self.assertTrue(get_test_template(False).create_for_reservation(
        get_test_reservation(True)))

  def test_do_not_create_overdue(self):
    get_test_template(
        True,
        offset=5,
        days_or_hours=DAYS,
        before_or_after=BEFORE,
        triggering_event=CHECKIN)
    do_not = get_test_reservation(True, check_in=now())
    self.assertEqual(0, len(Message.objects.create_for_reservation(do_not)))
    do_create = get_test_reservation(
        True, check_in=now() + timedelta(days=6))
    self.assertEqual(1, len(Message.objects.create_for_reservation(do_create)))


class MessageTests(TestCase):
  def test_send_sms_failed_alerts(self):
    reservation = get_test_reservation(True, check_in=now())
    get_test_template(
        True,
        offset=1,
        days_or_hours=HOURS,
        before_or_after=BEFORE,
        triggering_event=CHECKIN)
    self.assertEqual(
        1, len(Message.objects.create_for_reservation(reservation)))

    mock_front = Mock(spec=Front)

    class FakeBadResult(object):
      ok = False
    mock_front.send_sms.return_value = FakeBadResult()
    mock_sync = Mock(spec=ReservationSyncer)

    Message.objects.send(mock_sync, front=mock_front)

    self.assertEqual(
        [call(reservation)], mock_sync.alert_send_sms_failed.call_args_list)

  def test_create_for_reservation(self):
    green_change = get_test_template(
        True,
        guesty_custom_field_id='green',
        offset=1,
        days_or_hours=DAYS,
        before_or_after=AFTER,
        triggering_event=CHECKOUT,
        at_time=time(9, 0),
        message='Original message')
    blue_chuck = get_test_template(
        True,
        guesty_custom_field_id='blue',
        offset=2,
        days_or_hours=HOURS,
        before_or_after=BEFORE,
        triggering_event=CHECKIN)

    r = get_test_reservation(
        True,
        check_in=now(),
        check_out=now() + timedelta(days=1))
    self.assertEqual(2, len(Message.objects.create_for_reservation(r)))
    green = Message.objects.get(reservation=r, guesty_custom_field_id='green')
    self.assertEqual(
        (now() + timedelta(days=2)).date(), green.when_should.date())

    blue_chuck.delete()
    green_change.message = 'Updated message'
    green_change.save()

    get_test_template(
        True,
        guesty_custom_field_id='red',
        offset=3,
        days_or_hours=HOURS,
        before_or_after=BEFORE,
        triggering_event=CHECKIN)

    r.check_out += timedelta(days=1)
    r.save()
    Message.objects.create_for_reservation(r)

    messages = Message.objects.get_for_reservation(r)
    got = list([m.guesty_custom_field_id for m in messages])
    self.assertEqual(['red', 'green'], got)
    green = Message.objects.get(reservation=r, guesty_custom_field_id='green')
    self.assertEqual(green.message, 'Updated message')
    self.assertEqual(
        (now() + timedelta(days=3)).date(), green.when_should.date())

  def test_send_id_verification(self):
    get_test_template(
        True,
        guesty_custom_field_id='green',
        offset=1,
        days_or_hours=HOURS,
        before_or_after=BEFORE,
        triggering_event=CHECKIN,
        message='Whenre yuh gonna verify ID?',
        special_purpose=ID_VERIFICATION_REQUIRED)

    has_id_verification = get_test_reservation(
        True, check_in=now(),
        check_out=now() + timedelta(days=1),
        channel_reservation_id='IBeieveInA', id_verified=True,
        phone='111-111-1111')
    has_id_message = Message.objects.create_for_reservation(
        has_id_verification)[0]

    does_not_have_id_verification = get_test_reservation(
        True, check_in=now(),
        check_out=now() + timedelta(days=1),
        channel_reservation_id='ThingCalledLove', id_verified=False,
        phone='222-222-2222')
    does_not_have_id_message = Message.objects.create_for_reservation(
        does_not_have_id_verification)[0]

    front = Mock(spec=Front)
    front.send_sms.return_value = FakeSendSMSResult()
    sync = Mock(spec=ReservationSyncer)

    Message.objects.send(sync, front=front)

    self.assertEqual([call(
        '222-222-2222',
        'Whenre yuh gonna verify ID?')], front.send_sms.call_args_list)
    expected_calls = [
        call(has_id_verification),
        call(does_not_have_id_verification)]
    self.assertEqual(
        expected_calls, sync.sync_stayd_reservation.call_args_list)

    has_id_message.refresh_from_db()
    self.assertEqual(
        has_id_message.why_did_not_send,
        'ID_VERIFICATION_REQUIRED but the id is verified already.')
    self.assertIsNone(has_id_message.send_results)

    does_not_have_id_message.refresh_from_db()
    self.assertIsNotNone(does_not_have_id_message.send_results)
    self.assertEqual('222-222-2222', does_not_have_id_message.sent_to_phone)

  def test_alert_overdue_messages(self):
    clock = Mock(spec=Clock)
    now = parse_datetime('2018-05-30T17:18:59.922139+00:00')
    clock.now.return_value = now

    template = get_test_template(
        True, message='Blargh!', special_purpose=ID_VERIFICATION_REQUIRED)

    reason_why_not = template.create_for_reservation(
        get_test_reservation(True))
    reason_why_not.why_did_not_send = 'It\'s ok, this shouldn\'t send.'
    reason_why_not.when_should = now - timedelta(hours=7)
    reason_why_not.save()

    not_yet_overdue = template.create_for_reservation(
        get_test_reservation(True))
    not_yet_overdue.when_should = now - timedelta(hours=5)
    not_yet_overdue.save()

    overdue_but_shoulndt = template.create_for_reservation(
        get_test_reservation(True, id_verified=True, phone='444-555-6666'))
    overdue_but_shoulndt.when_should = now - timedelta(hours=7)
    overdue_but_shoulndt.save()

    overdue_reservation = get_test_reservation(
        True,
        phone='111-222-3333',
        full_name='Dave',
        nickname='Buckingham Palace')
    overdue = template.create_for_reservation(overdue_reservation)
    overdue.when_should = now - timedelta(hours=7)
    overdue.save()

    error_logger = Mock(spec=ErrorLogger)

    for i in range(2):
      Message.objects.notify_overdue_messages(
          clock=clock, error_logger=error_logger)

    expected_message = (
        'These messages didn\'t go out on time and must now be handled '
        'manually:\n\n111-222-3333 Dave Buckingham Palace Reservation id {}\n'
        'Blargh!\nShould have sent 7 hours ago').format(overdue_reservation.pk)
    self.assertEqual(error_logger.log_error.call_args_list, [call(
        'Long overdue messages', expected_message, always_new_error=True)])

  def test_should_send_not_confirmed(self):
    template = get_test_template(True)
    should_not = get_test_reservation(True, status='not confirmed')
    should = get_test_reservation(True)
    self.assertFalse(Message.objects._should_send(
        template.create_for_reservation(should_not)))
    self.assertTrue(
        Message.objects._should_send(template.create_for_reservation(should)))

  def test_should_send_id_required_id_submission_exists(self):
    from id_verify.tests import get_test_submission
    template = get_test_template(
        True, offset=25,
        days_or_hours=HOURS,
        before_or_after=AFTER,
        triggering_event=CHECKIN,
        special_purpose=ID_VERIFICATION_REQUIRED)

    # check_in is before go-live
    should_not_reservation = get_test_reservation(
        True, channel=AIRBNB, check_in=now() + timedelta(days=1))
    get_test_submission(True, reservation=should_not_reservation)
    self.assertFalse(Message.objects._should_send(
        template.create_for_reservation(should_not_reservation)))

    should_reservation = get_test_reservation(
        True, channel=AIRBNB, check_in=now() + timedelta(days=1))
    should_send_message = template.create_for_reservation(should_reservation)
    self.assertTrue(Message.objects._should_send(should_send_message))

  def test_should_send_morning_after(self):
    template = get_test_template(
        True, special_purpose=MORNING_AFTER_ARRIVAL)
    should_not = get_test_reservation(
        True, night_count=1, id_verified=True)
    should = get_test_reservation(
        True, night_count=2, id_verified=True)
    self.assertFalse(Message.objects._should_send(
        template.create_for_reservation(should_not)))
    self.assertIsNone(
        template.create_for_reservation(should).explain_why_do_not_send())

  def test_should_send_payment_and_id(self):
    template = get_test_template(
        True, special_purpose=PAYMENT_DEPOSIT_ID_RECEIVED)

    r = get_test_reservation(
        True, channel=AIRBNB, id_verified=False, is_paid_in=False,
        security_deposit=None)
    self.assertFalse(
        Message.objects._should_send(template.create_for_reservation(r)))
    # Airbnb handles payment risk so we only care about id verification here.
    r.id_verified = True
    self.assertIsNone(
        template.create_for_reservation(r).explain_why_do_not_send())
    # But for the other channels, all 3 need to be in place.
    r.listing.channel = BOOKINGCOM
    self.assertFalse(
        Message.objects._should_send(template.create_for_reservation(r)))
    r.is_paid_in = True
    self.assertFalse(
        Message.objects._should_send(template.create_for_reservation(r)))
    r.security_deposit = Money(10, 'USD')
    self.assertTrue(
        Message.objects._should_send(template.create_for_reservation(r)))

  def test_send(self):
    get_test_template(
        True,
        guesty_custom_field_id='green',
        offset=1,
        days_or_hours=HOURS,
        before_or_after=BEFORE,
        triggering_event=CHECKIN,
        message='before {delay} after')

    should_have_sent = []
    should_not_have_sent = []
    long_ago = get_test_reservation(
        True, check_in=now() - timedelta(days=20),
        check_out=now() - timedelta(days=18),
        phone='197-287-3756', airvatar_name='Steve')
    should_not_have_sent.extend(
        Message.objects.create_for_reservation(long_ago))
    not_yet = get_test_reservation(
        True, check_in=now() + timedelta(hours=2),
        check_out=now() + timedelta(days=1),
        phone='954-129-7632', airvatar_name='Abraham')
    should_not_have_sent.extend(
        Message.objects.create_for_reservation(not_yet))
    recent_1 = get_test_reservation(
        True, check_in=now() - timedelta(hours=1),
        check_out=now() + timedelta(hours=23),
        phone='111-111-1111', airvatar_name='Fatima')
    should_have_sent.extend(
        Message.objects.create_for_reservation(recent_1))
    recent_2 = get_test_reservation(
        True, check_in=now(),
        check_out=now() + timedelta(days=1),
        phone='999-999-9999', airvatar_name='Joe')
    should_have_sent.extend(
        Message.objects.create_for_reservation(recent_2))

    clock = Mock(spec=Clock)
    clock.elapsed_seconds.return_value = 1
    front = Mock(spec=Front)
    front.send_sms.return_value = FakeSendSMSResult()

    sync = Mock(spec=ReservationSyncer)
    Message.objects.send(sync, front=front, clock=clock)

    self.assertEqual([call(44)], clock.sleep.call_args_list)
    self.assertEqual([
        call('111-111-1111', 'before'),
        call('999-999-9999', 'before'),
        call('111-111-1111', 'after'),
        call('999-999-9999', 'after')],
        front.send_sms.call_args_list)
    for guest_message in should_not_have_sent:
      loaded = Message.objects.get(pk=guest_message.pk)
      self.assertFalse(bool(loaded.when_did))
    for guest_message in should_have_sent:
      loaded = Message.objects.get(pk=guest_message.pk)
      self.assertTrue(bool(loaded.when_did))

  def test_verify_delivery(self):
    hour_ago = now() - timedelta(hours=1)
    no_problem = get_test_message(
        True, send_results=str({'message_uid': 'blue'}),
        delivery_check_on=None, delivery_error=None, when_should=hour_ago)
    problem = get_test_message(
        True, send_results=str({'message_uid': 'green'}),
        delivery_check_on=None, delivery_error=None, when_should=hour_ago,
        full_name='The Queen of Spain', phone='123-456-7890',
        sent_to_phone='999-888-7777', message='Whats your fav color?')
    GuestyReservation.objects.create(
        reservation=problem.reservation, guesty_id='redblue')

    def delivery_error(message_uid):
      if message_uid == 'blue':
        return
      elif message_uid == 'green':
        return 'twilio_invalid_to'
      raise Exception(message_uid)

    front = Mock(spec=Front)
    front.delivery_error.side_effect = delivery_error
    error_logger = Mock(spec=ErrorLogger)

    Message.objects.verify_delivery(front=front, error_logger=error_logger)

    no_problem.refresh_from_db()
    problem.refresh_from_db()
    self.assertIsNotNone(no_problem.delivery_check_on)
    self.assertIsNone(no_problem.delivery_error)
    self.assertIsNotNone(problem.delivery_check_on)
    self.assertEqual('twilio_invalid_to', problem.delivery_error)

    message = (
        'The Queen of Spain\n'
        'https://app.guesty.com/reservations/redblue/guests\n'
        'sent to: 999-888-7777\n'
        'note: the guest\'s phone number is now 123-456-7890\n'
        'error: twilio_invalid_to\n'
        'Whats your fav color?')

    self.assertEqual(error_logger.log_error.call_args_list, [call(
        'SMS delivery errors',
        message,
        extra_to=settings.ALERT_BAD_PHONE,
        always_new_error=True)])
