from datetime import datetime, timedelta
from unittest.mock import Mock, call

from django.test import TestCase
from django.utils import timezone
from django.utils.timezone import make_aware

from guest_messages.models import (
    Template, Message, DAYS, HOURS, BEFORE, AFTER, CHECKIN, CHECKOUT)
from reservations.tests import get_test_reservation
from util.channels import AIRBNB, BOOKINGCOM
from util.clock import Clock
from util.front import Front


def get_test_template(create, **kwargs):
  template = Template(
      guesty_custom_field_name=kwargs.get('guesty_custom_field_name', 'foo'),
      special_purpose=kwargs.get('special_purpose', ''),
      offset=kwargs.get('offset', 1),
      days_or_hours=kwargs.get('days_or_hours', DAYS),
      before_or_after=kwargs.get('before_or_after', BEFORE),
      checkin_or_checkout=kwargs.get('checkin_or_checkout', CHECKIN),
      message=kwargs.get('message', 'Here\'s your message!'))
  if create:
    template.save()
  return template


class TemplateTests(TestCase):
  def test_when_should_for_reservation(self):
    r = get_test_reservation(
        False, check_in=make_aware(datetime(2018, 3, 7, 15)),
        check_out=make_aware(datetime(2018, 3, 9, 11)))
    t = get_test_template(False)

    t.offset = 2
    t.days_or_hours = DAYS
    t.before_or_after = BEFORE
    t.checkin_or_checkout = CHECKIN
    self.assertEqual(
        make_aware(datetime(2018, 3, 5, 15)),
        t.when_should_for_reservation(r))

    t.offset = 3
    t.days_or_hours = HOURS
    t.before_or_after = AFTER
    t.checkin_or_checkout = CHECKOUT
    self.assertEqual(
        make_aware(datetime(2018, 3, 9, 14)),
        t.when_should_for_reservation(r))

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
        guesty_custom_field_name='green',
        offset=1,
        days_or_hours=HOURS,
        before_or_after=BEFORE,
        checkin_or_checkout=CHECKIN)
    blue_chuck = get_test_template(
        True,
        guesty_custom_field_name='blue',
        offset=2,
        days_or_hours=HOURS,
        before_or_after=BEFORE,
        checkin_or_checkout=CHECKIN)

    r = get_test_reservation(True)
    Message.objects.create_for_reservation(r)

    blue_chuck.delete()

    get_test_template(
        True,
        guesty_custom_field_name='red',
        offset=3,
        days_or_hours=HOURS,
        before_or_after=BEFORE,
        checkin_or_checkout=CHECKIN)

    Message.objects.create_for_reservation(r)

    messages = Message.objects.get_for_reservation(r)
    got = list([m.guesty_custom_field_name for m in messages])
    self.assertEqual(['red', 'green'], got)

  def test_send(self):
    Template.objects.all().delete()
    get_test_template(
        True,
        guesty_custom_field_name='green',
        offset=1,
        days_or_hours=HOURS,
        before_or_after=BEFORE,
        checkin_or_checkout=CHECKIN,
        message='before{delay}after')

    long_ago = get_test_reservation(
        True, check_in=timezone.now() - timedelta(days=20),
        check_out=timezone.now() - timedelta(days=18), front_channel='cha_123',
        phone='aaa-aaa-aaaa', airvatar_name='Steve')
    Message.objects.create_for_reservation(long_ago)
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
