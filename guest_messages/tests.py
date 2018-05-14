from datetime import datetime, timedelta
from unittest.mock import Mock, call

from django.test import TestCase
from django.utils import timezone
from django.utils.timezone import make_aware

from guest_messages.models import (
    Template, Message, DAYS, HOURS, BEFORE, AFTER, CHECKIN, CHECKOUT,
    GUEST_FIRST_NAME, ADDRESS, IF_WE_REVIEW_THEM, DELAY)
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
    Template.objects.delete()
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
    assertEqual(['red', 'green'], got)

  def test_send(self):
    r0 = get_test_reservation(
        True, check_in=timezone.now() - timedelta(days=20),
        check_out=timezone.now() - timedelta(days=18))
    r1 = get_test_reservation(
        True, check_in=timezone.now(),
        check_out=timezone.now() + timedelta(days=1))
    r2 = get_test_reservation(
        True, check_in=timezone.now() - timedelta(hours=1),
        check_out=timezone.now() + timedelta(hours=23))

    Template.objects.delete()
    get_test_template(
        True,
        guesty_custom_field_name='green',
        offset=1,
        days_or_hours=HOURS,
        before_or_after=BEFORE,
        checkin_or_checkout=CHECKIN,
        message='before{delay}after')

    Message.objects.create_for_reservation(r0)
    Message.objects.create_for_reservation(r1)
    Message.objects.create_for_reservation(r2)

    clock = Mock(spec=Clock)
    front = Mock(spec=Front)
    Message.objects.send(front=front, clock=clock)

send_sms(self, to, from_channel, content)

    self.assertEqual([call(30)], clock.sleep.call_args_list())
    self.assertEqual([], front.send_sms)
