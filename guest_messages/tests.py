from datetime import datetime, timedelta, time
from unittest.mock import Mock, call

from django.test import TestCase
from django.utils import timezone
from django.utils.timezone import make_aware

from guest_messages.models import (
    Template, Message, DAYS, HOURS, BEFORE, AFTER, CHECKIN, CHECKOUT,
    BOOKING, ID_VERIFICATION_REQUIRED)
from reservations.models import Reservation
from reservations.tests import get_test_reservation
from util.channels import AIRBNB, BOOKINGCOM
from util.clock import Clock
from util.front import Front
from util.timezone import str_to_tz_dt


def get_test_template(create, **kwargs):
  template = Template(
      guesty_custom_field_id=kwargs.get('guesty_custom_field_id', 'foo'),
      special_purpose=kwargs.get('special_purpose', ''),
      offset=kwargs.get('offset', 1),
      days_or_hours=kwargs.get('days_or_hours', DAYS),
      before_or_after=kwargs.get('before_or_after', BEFORE),
      triggering_event=kwargs.get('triggering_event', CHECKIN),
      message=kwargs.get('message', 'Here\'s your message!'))
  if create:
    template.save()
  return template


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
        t.when_should_for_reservation(r))

    t.offset = 3
    t.days_or_hours = HOURS
    t.before_or_after = AFTER
    t.triggering_event = CHECKOUT
    self.assertEqual(
        make_aware(datetime(2018, 3, 9, 14)),
        t.when_should_for_reservation(r))

    t.triggering_event = BOOKING
    self.assertEqual(
        make_aware(datetime(2018, 3, 2, 16)),
        t.when_should_for_reservation(r))

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
        t.when_should_for_reservation(r_loaded))

  def test_message_for_reservation(self):
    r = get_test_reservation(False)
    r.listing.channel = AIRBNB
    r.listing.rental.airbnb_address_scrape = '43 Spud Dr., Idaho'
    r.guest.first_name = 'Jill'
    t = get_test_template(False)
    t.message = (
        'Hello {guest_first_name}!{delay}Your reservation is at {address}.'
        '{if_we_review_them} We will review you.{/}')
    expected = (
        'Hello Jill!{delay}Your reservation is at 43 Spud Dr., Idaho.'
        ' We will review you.')
    self.assertEqual(expected, t.message_for_reservation(r))

    r.listing.channel = BOOKINGCOM
    expected = (
        'Hello Jill!{delay}Your reservation is at 43 Spud Dr., Idaho.')
    self.assertEqual(expected, t.message_for_reservation(r))

  def test_create_for_reservation(self):
    self.assertTrue(get_test_template(False).create_for_reservation(
        get_test_reservation(True)))


class MessageTests(TestCase):
  def test_create_for_reservation(self):
    Template.objects.all().delete()
    get_test_template(
        True,
        guesty_custom_field_id='green',
        offset=1,
        days_or_hours=HOURS,
        before_or_after=BEFORE,
        triggering_event=CHECKIN)
    blue_chuck = get_test_template(
        True,
        guesty_custom_field_id='blue',
        offset=2,
        days_or_hours=HOURS,
        before_or_after=BEFORE,
        triggering_event=CHECKIN)

    r = get_test_reservation(True)
    Message.objects.create_for_reservation(r)

    blue_chuck.delete()

    get_test_template(
        True,
        guesty_custom_field_id='red',
        offset=3,
        days_or_hours=HOURS,
        before_or_after=BEFORE,
        triggering_event=CHECKIN)

    Message.objects.create_for_reservation(r)

    messages = Message.objects.get_for_reservation(r)
    got = list([m.guesty_custom_field_id for m in messages])
    self.assertEqual(['red', 'green'], got)

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
        True, check_in=timezone.now(),
        check_out=timezone.now() + timedelta(days=1),
        channel_reservation_id='IBeieveInA', id_verified=True,
        phone='111-111-1111')
    Message.objects.create_for_reservation(has_id_verification)

    does_not_have_id_verification = get_test_reservation(
        True, check_in=timezone.now(),
        check_out=timezone.now() + timedelta(days=1),
        channel_reservation_id='ThingCalledLove', id_verified=False,
        phone='222-222-2222')
    Message.objects.create_for_reservation(does_not_have_id_verification)

    front = Mock(spec=Front)
    Message.objects.send(front=front)

    self.assertEqual(
        [call('222-222-2222', 'cha_637r', 'Whenre yuh gonna verify ID?')],
        front.send_sms.call_args_list)

  def test_send(self):
    get_test_template(
        True,
        guesty_custom_field_id='green',
        offset=1,
        days_or_hours=HOURS,
        before_or_after=BEFORE,
        triggering_event=CHECKIN,
        message='before{delay}after')

    long_ago = get_test_reservation(
        True, check_in=timezone.now() - timedelta(days=20),
        check_out=timezone.now() - timedelta(days=18), front_channel='cha_123',
        phone='aaa-aaa-aaaa', airvatar_name='Steve')
    Message.objects.create_for_reservation(long_ago)
    not_yet = get_test_reservation(
        True, check_in=timezone.now() + timedelta(hours=2),
        check_out=timezone.now() + timedelta(days=1), front_channel='cha_789',
        phone='ccc-ccc-cccc', airvatar_name='Abraham')
    Message.objects.create_for_reservation(not_yet)
    recent_1 = get_test_reservation(
        True, check_in=timezone.now() - timedelta(hours=1),
        check_out=timezone.now() + timedelta(hours=23), front_channel='cha_a',
        phone='111-111-1111', airvatar_name='Fatima')
    Message.objects.create_for_reservation(recent_1)
    recent_2 = get_test_reservation(
        True, check_in=timezone.now(),
        check_out=timezone.now() + timedelta(days=1), front_channel='cha_z',
        phone='999-999-9999', airvatar_name='Joe')
    Message.objects.create_for_reservation(recent_2)
    auto_communicate_off = get_test_reservation(
        True, auto_communicate=False, check_in=timezone.now(),
        check_out=timezone.now() + timedelta(days=1), front_channel='cha_456',
        phone='bbb-bbb-bbbb', airvatar_name='Patricia')
    Message.objects.create_for_reservation(auto_communicate_off)

    clock = Mock(spec=Clock)
    clock.elapsed_seconds.return_value = 1
    front = Mock(spec=Front)

    Message.objects.send(front=front, clock=clock)

    # send_sms(self, to, from_channel, content)

    self.assertEqual([call(29)], clock.sleep.call_args_list)
    self.assertEqual([
        call('111-111-1111', 'cha_a', 'before'),
        call('999-999-9999', 'cha_z', 'before'),
        call('111-111-1111', 'cha_a', 'after'),
        call('999-999-9999', 'cha_z', 'after')],
        front.send_sms.call_args_list)
