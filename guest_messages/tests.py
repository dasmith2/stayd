from datetime import datetime, timedelta, time
from unittest.mock import Mock, call

from util.tests import TestCase
from django.conf import settings
from django.utils.dateparse import parse_datetime
from django.utils.timezone import make_aware, now
from djmoney.money import Money

from errors.models import ErrorLogger
from guest_messages.mandrill import Emailer
from guest_messages.mandrill_examples import SEND_RESULT
from guest_messages.models import (
    ReservationSyncer, SMSTemplate, EmailTemplate, SMS, Email)
from guest_messages.models_base import (
    DAYS, HOURS, BEFORE, AFTER, CHECKIN, CHECKOUT, BOOKING,
    ID_VERIFICATION_REQUIRED, PAYMENT_DEPOSIT_ID_RECEIVED,
    MORNING_AFTER_ARRIVAL)
from guest_messages.template_tags import TemplateTags
from guesty.models import GuestyReservation
from reservations.models import Reservation
from reservations.tests import get_test_reservation
from util.channels import AIRBNB, BOOKINGCOM, HOMEAWAY
from util.clock import Clock
from util.timezone import parse_dt
from front.models import Front, FakeSendSMSResult
from util.timezone import str_to_tz_dt, morning_from_date, afternoon_from_date


def get_test_smstemplate(create, **kwargs):
  template = SMSTemplate(
      message=kwargs.get('message', 'Here\'s your message!'))
  _get_test_template_helper(template, **kwargs)
  if create:
    template.save()
  return template


def get_test_emailtemplate(create, **kwargs):
  template = EmailTemplate(
      mailchimp_template=kwargs.get('mailchimp_template', 'My template'),
      subject=kwargs.get('subject', 'Subject here'))
  _get_test_template_helper(template, **kwargs)
  if create:
    template.save()
  return template


def _get_test_template_helper(template, **kwargs):
  template.triggering_event = kwargs.get('triggering_event', None)
  template.pre_scheduled = kwargs.get('pre_scheduled', True)
  template.preschedule_around = kwargs.get('preschedule_around', CHECKIN)
  template.offset = kwargs.get('offset', 1)
  template.days_or_hours = kwargs.get('days_or_hours', DAYS)
  template.before_or_after = kwargs.get('before_or_after', BEFORE)
  template.at_time = kwargs.get('at_time', None)
  template.check_before_sending = kwargs.get('check_before_sending', '')
  template.guesty_custom_field_id = kwargs.get(
      'guesty_custom_field_id', 'foo')
  template.allowed_hours_late = kwargs.get('allowed_hours_late', 6)


def get_test_email(create, **kwargs):
  template = get_test_emailtemplate(create, **kwargs)

  message = Email(
      template=kwargs.get('template', template),
      send_results=kwargs.get('send_results', SEND_RESULT),
      subject=kwargs.get('subject', 'Hello mars'),
      sent_to=kwargs.get('sent_to', 'dave@doov.dang'))
  _get_test_message_helper(message, create, **kwargs)

  if create:
    message.save()
  return message


def get_test_sms(create, **kwargs):
  template = get_test_smstemplate(create, **kwargs)
  send_results = (
      "{'conversation_reference': "
      "'0013425ed607a418e4866e16be52612a@frontapp.com', 'message_uid': "
      "'0013425ed607a418e4866e16be52612a', 'status': 'accepted'}")

  guest_message = SMS(
      template=kwargs.get('template', template),
      send_results=kwargs.get('send_results', send_results),
      message=kwargs.get('message', 'Hello world'),
      sent_to=kwargs.get('sent_to', '555-555-5555'))
  _get_test_message_helper(guest_message, create, **kwargs)

  if create:
    guest_message.save()
  return guest_message


def _get_test_message_helper(guest_message, create, **kwargs):
  reservation = get_test_reservation(create, **kwargs)

  guest_message.reservation = kwargs.get('reservation', reservation)
  guest_message.when_should = kwargs.get(
      'when_should', now() - timedelta(hours=1))
  guest_message.when_did = kwargs.get('when_did', now() - timedelta(hours=1))
  guest_message.green_light = kwargs.get('green_light', True)
  guest_message.why_did_not_send = kwargs.get('why_did_not_send', '')
  guest_message.delivery_check_on = kwargs.get('delivery_check_on', None)
  guest_message.delivery_error = kwargs.get('delivery_error', None)


class TemplateTests(TestCase):
  def test_when_should_offset_only_no_specific_time(self):
    r = get_test_reservation(
        False, booked_at=make_aware(datetime(2018, 3, 2, 13)),
        check_in=make_aware(datetime(2018, 3, 7, 15)),
        check_out=make_aware(datetime(2018, 3, 9, 11)))
    t = get_test_smstemplate(False)

    t.offset = 2
    t.days_or_hours = DAYS
    t.before_or_after = BEFORE
    t.preschedule_around = CHECKIN
    self.assertEqual(
        make_aware(datetime(2018, 3, 5, 15)),
        t.when_should(r))

    t.offset = 3
    t.days_or_hours = HOURS
    t.before_or_after = AFTER
    t.preschedule_around = CHECKOUT
    self.assertEqual(
        make_aware(datetime(2018, 3, 9, 14)),
        t.when_should(r))

    t.preschedule_around = BOOKING
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

    t = get_test_smstemplate(False)
    t.offset = 0
    t.days_or_hours = DAYS
    t.before_or_after = AFTER
    t.preschedule_around = CHECKOUT
    t.at_time = time(9)
    self.assertEqual(
        str_to_tz_dt('2018-03-02 09:00:00', 'US/Hawaii'),
        t.when_should(r_loaded))

  def test_get_message_string(self):
    r = get_test_reservation(
        True, channel=AIRBNB, airbnb_address_scrape='43 Spud Dr., Idaho',
        city='Austin', first_name='Jill', email='jill@gmail.com',
        main_checkin_instructions_link=(
            'main checkin instructions link'),
        main_property_access_codes_in_order_of_use=(
            'main property access codes in order of use'),
        master_access_code_building_door_electronic_lock=(
            'master access code building door electronic lock'),
        master_access_code_apartment_door_electronic_lock=(
            'master access code apartment door electronic lock'),
        wifi_network_name=(
            'wifi network name'),
        wifi_password=(
            'wifi password'),
        building_trash_instructions=(
            'building trash instructions'),
        link_to_property_page_in_helpdocs=(
            'link to property page in helpdocs'),
        google_maps_link=(
            'google maps link'),
        departure_check_list=(
            'departure check list'),
        local_bag_storage_info=(
            'local bag storage info'),
        local_bag_storage_link=(
            'local bag storage link'),
        parking_link=(
            'parking link'),
        public_transportation_link=(
            'public transportation link'),
        local_recommendations_link=(
            'local recommendations link'),
        walking_to_nearest_path_stations=(
            'walking to nearest path stations'),
        parking_suggestions_no_links=(
            'parking suggestions no links'),
        public_transport_no_link=(
            'public transport no link'),
        walk_time_to_nearest_train=(
            'walk time to nearest train'),
        laundry_info=(
            'laundry info'))
    r = Reservation.objects.get(pk=r.pk)
    t = get_test_smstemplate(False)
    t.message = (
        'Hello {{guest_first_name}}!{delay}Your reservation is at {address}. '
        'I see you love {Airbnb}A1rbnb{/}{Booking.com}B00king.com{/}'
        '{Homeaway}Home@way{/}.')
    expected = (
        'Hello Jill!{delay}Your reservation is at 43 Spud Dr., Idaho. '
        'I see you love A1rbnb.')
    self.assertEqual(expected, t.get_message_string(r))

    r.channel = BOOKINGCOM
    expected = (
        'Hello Jill!{delay}Your reservation is at 43 Spud Dr., Idaho. '
        'I see you love B00king.com.')
    self.assertEqual(expected, t.get_message_string(r))

    r.channel = HOMEAWAY
    expected = (
        'Hello Jill!{delay}Your reservation is at 43 Spud Dr., Idaho. '
        'I see you love Home@way.')
    self.assertEqual(expected, t.get_message_string(r))

    t.message = 'See {guest_email} re your stay in {city}'
    expected = 'See jill@gmail.com re your stay in Austin'
    self.assertEqual(expected, t.get_message_string(r))

    r.channel = AIRBNB
    t.message = '{id_verify_link}'
    expected = 'https://guests.stayd.com/verify_id/?name=Ron+Burgundy'
    self.assertEqual(expected, t.get_message_string(r))

    t.message = '{main_checkin_instructions_link}'
    self.assertEqual(
        'main checkin instructions link', t.get_message_string(r))
    t.message = '{main_property_access_codes_in_order_of_use}'
    self.assertEqual(
        'main property access codes in order of use', t.get_message_string(r))
    t.message = '{master_access_code_building_door_electronic_lock}'
    self.assertEqual(
        'master access code building door electronic lock',
        t.get_message_string(r))
    t.message = '{master_access_code_apartment_door_electronic_lock}'
    self.assertEqual(
        'master access code apartment door electronic lock',
        t.get_message_string(r))
    t.message = '{wifi_network_name}'
    self.assertEqual(
        'wifi network name', t.get_message_string(r))
    t.message = '{wifi_password}'
    self.assertEqual(
        'wifi password', t.get_message_string(r))
    t.message = '{building_trash_instructions}'
    self.assertEqual(
        'building trash instructions', t.get_message_string(r))
    t.message = '{link_to_property_page_in_helpdocs}'
    self.assertEqual(
        'link to property page in helpdocs', t.get_message_string(r))
    t.message = '{google_maps_link}'
    self.assertEqual(
        'google maps link', t.get_message_string(r))
    t.message = '{departure_check_list}'
    self.assertEqual(
        'departure check list', t.get_message_string(r))
    t.message = '{local_bag_storage_info}'
    self.assertEqual(
        'local bag storage info', t.get_message_string(r))
    t.message = '{local_bag_storage_link}'
    self.assertEqual(
        'local bag storage link', t.get_message_string(r))
    t.message = '{parking_link}'
    self.assertEqual(
        'parking link', t.get_message_string(r))
    t.message = '{public_transportation_link}'
    self.assertEqual(
        'public transportation link', t.get_message_string(r))
    t.message = '{local_recommendations_link}'
    self.assertEqual(
        'local recommendations link', t.get_message_string(r))
    t.message = '{walking_to_nearest_path_stations}'
    self.assertEqual(
        'walking to nearest path stations', t.get_message_string(r))
    t.message = '{parking_suggestions_no_links}'
    self.assertEqual(
        'parking suggestions no links', t.get_message_string(r))
    t.message = '{public_transport_no_link}'
    self.assertEqual(
        'public transport no link', t.get_message_string(r))
    t.message = '{walk_time_to_nearest_train}'
    self.assertEqual(
        'walk time to nearest train', t.get_message_string(r))
    t.message = '{laundry_info}'
    self.assertEqual(
        'laundry info', t.get_message_string(r))

  def test_create_new_message(self):
    template = get_test_smstemplate(True)
    message = template.create_new_message(get_test_reservation(True))
    self.assertEqual(message.template, template)

  def test_do_not_create_overdue(self):
    get_test_smstemplate(
        True,
        offset=5,
        days_or_hours=DAYS,
        before_or_after=BEFORE,
        preschedule_around=CHECKIN)
    do_not = get_test_reservation(True, check_in=now())
    self.assertEqual(0, len(
        SMS.objects.create_prescheduled_for_reservation(do_not)))
    do_create = get_test_reservation(
        True, check_in=now() + timedelta(days=6))
    self.assertEqual(1, len(
        SMS.objects.create_prescheduled_for_reservation(do_create)))


class MessageTests(TestCase):
  def test_create_new_message(self):
    green_change = get_test_smstemplate(
        True,
        guesty_custom_field_id='green',
        offset=1,
        days_or_hours=DAYS,
        before_or_after=AFTER,
        preschedule_around=CHECKOUT,
        at_time=time(9, 0),
        message='Original message')
    blue_chuck = get_test_smstemplate(
        True,
        guesty_custom_field_id='blue',
        offset=2,
        days_or_hours=HOURS,
        before_or_after=BEFORE,
        preschedule_around=CHECKIN)

    check_in = afternoon_from_date(now())
    check_out = morning_from_date(now() + timedelta(days=1))
    r = get_test_reservation(True, check_in=check_in, check_out=check_out)

    self.assertEqual(2, len(
        SMS.objects.create_prescheduled_for_reservation(r)))
    green = SMS.objects.get(
        reservation=r, template__guesty_custom_field_id='green')
    self.assertEqual(
        (check_out + timedelta(days=1)).date(), green.when_should.date())

    blue_chuck.delete()
    green_change.message = 'Updated message'
    green_change.save()

    get_test_smstemplate(
        True,
        guesty_custom_field_id='red',
        offset=3,
        days_or_hours=HOURS,
        before_or_after=BEFORE,
        preschedule_around=CHECKIN)

    r.check_out += timedelta(days=1)
    r.save()
    SMS.objects.create_prescheduled_for_reservation(r)

    messages = SMS.objects.get_for_reservation(r)
    got = list([m.guesty_custom_field_id() for m in messages])
    self.assertEqual(['red', 'green'], got)
    green = SMS.objects.get(
        reservation=r, template__guesty_custom_field_id='green')
    self.assertEqual(green.message, 'Updated message')
    self.assertEqual(
        (check_out + timedelta(days=2)).date(), green.when_should.date())

  def test_send_id_verification(self):
    get_test_smstemplate(
        True,
        guesty_custom_field_id='green',
        offset=1,
        days_or_hours=HOURS,
        before_or_after=BEFORE,
        preschedule_around=CHECKIN,
        message='Whenre yuh gonna verify ID?',
        check_before_sending=ID_VERIFICATION_REQUIRED)

    has_id_verification = get_test_reservation(
        True, check_in=now(),
        check_out=now() + timedelta(days=1),
        channel_reservation_id='IBeieveInA', id_verified=True,
        phone='111-111-1111')
    has_id_message = SMS.objects.create_prescheduled_for_reservation(
        has_id_verification)[0]

    does_not_have_id_verification = get_test_reservation(
        True, check_in=now(),
        check_out=now() + timedelta(days=1),
        channel_reservation_id='ThingCalledLove', id_verified=False,
        phone='222-222-2222')
    does_not_have_id_message = SMS.objects.create_prescheduled_for_reservation(
        does_not_have_id_verification)[0]

    front = Mock(spec=Front)
    front.send_sms.return_value = FakeSendSMSResult()
    sync = Mock(spec=ReservationSyncer)

    SMS.objects.send(sync, front=front)

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
    self.assertEqual('222-222-2222', does_not_have_id_message.sent_to)

  def test_alert_overdue_smss(self):
    clock = Mock(spec=Clock)
    now = parse_datetime('2018-05-30T17:18:59.922139+00:00')
    clock.now.return_value = now

    template = get_test_smstemplate(
        True, message='Blargh!', check_before_sending=ID_VERIFICATION_REQUIRED,
        allowed_hours_late=9)

    reason_why_not = template.create_new_message(
        get_test_reservation(True))
    reason_why_not.why_did_not_send = 'It\'s ok, this shouldn\'t send.'
    reason_why_not.when_should = now - timedelta(hours=10)
    reason_why_not.save()

    not_yet_overdue = template.create_new_message(
        get_test_reservation(True))
    not_yet_overdue.when_should = now - timedelta(hours=8)
    not_yet_overdue.save()

    overdue_but_shoulndt = template.create_new_message(
        get_test_reservation(True, id_verified=True, phone='444-555-6666'))
    overdue_but_shoulndt.when_should = now - timedelta(hours=10)
    overdue_but_shoulndt.save()

    overdue_reservation = get_test_reservation(
        True,
        phone='111-222-3333',
        full_name='Dave',
        nickname='Buckingham Palace')
    overdue = template.create_new_message(overdue_reservation)
    overdue.when_should = now - timedelta(hours=10)
    overdue.save()

    error_logger = Mock(spec=ErrorLogger)

    for i in range(2):
      SMS.objects.notify_overdue_messages(
          clock=clock, error_logger=error_logger)

    expected_message = (
        'These SMSs didn\'t go out on time and must now be handled '
        'manually:\n\n111-222-3333 Dave Buckingham Palace Reservation id {}\n'
        'Blargh!\nShould have sent 10 hours ago').format(
        overdue_reservation.pk)
    self.assertEqual(error_logger.log_error.call_args_list, [call(
        'Long overdue SMSs', expected_message, always_new_error=True)])

  def test_alert_overdue_emails(self):
    clock = Mock(spec=Clock)
    now = parse_datetime('2018-12-15T17:18:59.922139+00:00')
    clock.now.return_value = now

    template = get_test_emailtemplate(
        True, subject='Heyooo', allowed_hours_late=9)

    overdue_reservation = get_test_reservation(
        True,
        email='dave@buckingham.com',
        full_name='Dave',
        nickname='Buckingham Palace')
    overdue = template.create_new_message(overdue_reservation)
    overdue.when_should = now - timedelta(hours=10)
    overdue.save()

    error_logger = Mock(spec=ErrorLogger)

    Email.objects.notify_overdue_messages(
        clock=clock, error_logger=error_logger)

    expected_message = (
        'These emails didn\'t go out on time and must now be handled '
        'manually:\n\ndave@buckingham.com Dave Buckingham Palace Reservation '
        'id {}\nHeyooo\nShould have sent 10 hours ago').format(
        overdue_reservation.pk)
    self.assertEqual(error_logger.log_error.call_args_list, [call(
        'Long overdue emails', expected_message, always_new_error=True)])

  def test_need_sending(self):
    template = get_test_smstemplate(
        True, allowed_hours_late=9,
        check_before_sending=ID_VERIFICATION_REQUIRED)
    old = template.create_new_message(
        get_test_reservation(True, id_verified=False))
    old.when_should = now() - timedelta(hours=10)
    old.save()

    newish = template.create_new_message(
        get_test_reservation(True, id_verified=False))
    newish.when_should = now() - timedelta(hours=8)
    newish.save()

    reason_why_not = template.create_new_message(
        get_test_reservation(True, id_verified=True))
    reason_why_not.when_should = now() - timedelta(hours=8)
    reason_why_not.save()

    sync = Mock(spec=ReservationSyncer)
    need_sending = list(SMS.objects.need_sending(sync, Clock(), False))
    self.assertEqual([newish], need_sending)

  def test_should_send_not_confirmed(self):
    template = get_test_smstemplate(True)
    should_not = get_test_reservation(True, status='not confirmed')
    should = get_test_reservation(True)
    self.assertFalse(template.create_new_message(should_not).should_send())
    self.assertTrue(template.create_new_message(should).should_send())

  def test_should_send_id_required_id_submission_exists(self):
    from id_verify.tests import get_test_submission
    template = get_test_smstemplate(
        True, offset=25,
        days_or_hours=HOURS,
        before_or_after=AFTER,
        preschedule_around=CHECKIN,
        check_before_sending=ID_VERIFICATION_REQUIRED)

    # check_in is before go-live
    should_not_reservation = get_test_reservation(
        True, channel=AIRBNB, check_in=now() + timedelta(days=1))
    get_test_submission(True, reservation=should_not_reservation)
    self.assertFalse(
        template.create_new_message(should_not_reservation).should_send())

    should_reservation = get_test_reservation(
        True, channel=AIRBNB, check_in=now() + timedelta(days=1))
    should_send_message = template.create_new_message(should_reservation)
    self.assertTrue(should_send_message.should_send())

  def test_should_send_morning_after(self):
    template = get_test_smstemplate(
        True, check_before_sending=MORNING_AFTER_ARRIVAL)
    should_not = get_test_reservation(
        True, night_count=1, id_verified=True)
    should = get_test_reservation(
        True, night_count=2, id_verified=True)
    self.assertFalse(template.create_new_message(should_not).should_send())
    self.assertIsNone(
        template.create_new_message(should).explain_why_do_not_send())

  def test_should_send_payment_and_id(self):
    template = get_test_smstemplate(
        True, check_before_sending=PAYMENT_DEPOSIT_ID_RECEIVED)

    r = get_test_reservation(
        True, channel=AIRBNB, id_verified=False, is_paid_in=False,
        security_deposit=None)
    self.assertFalse(template.create_new_message(r).should_send())
    # Airbnb handles payment risk so we only care about id verification here.
    r.id_verified = True
    self.assertIsNone(
        template.create_new_message(r).explain_why_do_not_send())
    # But for the other channels, all 3 need to be in place.
    r.channel = BOOKINGCOM
    self.assertFalse(template.create_new_message(r).should_send())
    r.is_paid_in = True
    self.assertFalse(template.create_new_message(r).should_send())
    r.security_deposit = Money(10, 'USD')
    self.assertTrue(template.create_new_message(r).should_send())

  def test_should_send_email_go_live(self):
    template = get_test_emailtemplate(
        True, mailchimp_template='My test template',
        subject='Hey {guest_first_name}',
        offset=0,
        days_or_hours=HOURS,
        before_or_after=BEFORE,
        preschedule_around=CHECKIN)
    early = template.create_new_message(get_test_reservation(True))
    early.when_should = parse_dt(settings.EMAIL_GOES_LIVE) - timedelta(hours=1)
    early.save()
    after = template.create_new_message(get_test_reservation(True))
    after.when_should = parse_dt(settings.EMAIL_GOES_LIVE) + timedelta(hours=1)
    after.save()

    self.assertFalse(early.should_send())
    self.assertTrue(after.should_send())

  def test_sendemail(self):
    get_test_emailtemplate(
        True, mailchimp_template='My test template',
        subject='Hey {guest_first_name}',
        offset=1,
        days_or_hours=HOURS,
        before_or_after=BEFORE,
        preschedule_around=CHECKIN)

    res = get_test_reservation(
        True, first_name='Hank', email='hank@hank.hank',
        check_in='2018-11-15 16:00', check_out='2018-11-17 11:00')
    Email.objects.create_prescheduled_for_reservation(res)

    sync = Mock(spec=ReservationSyncer)
    emailer = Mock(spec=Emailer)
    emailer.send_email.return_value = SEND_RESULT
    clock = Mock(spec=Clock)
    clock.now.return_value = parse_dt('2018-11-15 16:00')

    Email.objects.send(sync, emailer=emailer, clock=clock)

    template_params = TemplateTags().get_template_params_for_reservation(res)
    self.assertEqual(template_params['guest_first'], 'Hank')
    expected = [call(
        'Hey Hank', 'hank@hank.hank', template_params, 'My test template')]
    self.assertEqual(emailer.send_email.call_args_list, expected)

  def test_sendsms(self):
    get_test_smstemplate(
        True,
        guesty_custom_field_id='green',
        offset=1,
        days_or_hours=HOURS,
        before_or_after=BEFORE,
        preschedule_around=CHECKIN,
        message='before {delay} after')

    should_have_sent = []
    should_not_have_sent = []
    long_ago = get_test_reservation(
        True, check_in=now() - timedelta(days=20),
        check_out=now() - timedelta(days=18),
        phone='197-287-3756', airvatar_name='Steve')
    should_not_have_sent.extend(
        SMS.objects.create_prescheduled_for_reservation(long_ago))
    not_yet = get_test_reservation(
        True, check_in=now() + timedelta(hours=2),
        check_out=now() + timedelta(days=1),
        phone='954-129-7632', airvatar_name='Abraham')
    should_not_have_sent.extend(
        SMS.objects.create_prescheduled_for_reservation(not_yet))
    recent_1 = get_test_reservation(
        True, check_in=now() - timedelta(hours=1),
        check_out=now() + timedelta(hours=23),
        phone='111-111-1111', airvatar_name='Fatima')
    should_have_sent.extend(
        SMS.objects.create_prescheduled_for_reservation(recent_1))
    recent_2 = get_test_reservation(
        True, check_in=now(),
        check_out=now() + timedelta(days=1),
        phone='999-999-9999', airvatar_name='Joe')
    should_have_sent.extend(
        SMS.objects.create_prescheduled_for_reservation(recent_2))

    clock = Mock(spec=Clock)
    clock.elapsed_seconds.return_value = 1
    clock.now.return_value = now()
    front = Mock(spec=Front)
    front.send_sms.return_value = FakeSendSMSResult()

    sync = Mock(spec=ReservationSyncer)
    SMS.objects.send(sync, front=front, clock=clock)

    self.assertEqual([call(29)], clock.sleep.call_args_list)
    self.assertEqual([
        call('111-111-1111', 'before'),
        call('999-999-9999', 'before'),
        call('111-111-1111', 'after'),
        call('999-999-9999', 'after')],
        front.send_sms.call_args_list)
    for guest_message in should_not_have_sent:
      loaded = SMS.objects.get(pk=guest_message.pk)
      self.assertFalse(bool(loaded.when_did))
    for guest_message in should_have_sent:
      loaded = SMS.objects.get(pk=guest_message.pk)
      self.assertTrue(bool(loaded.when_did))

  def test_verify_smsdelivery(self):
    hour_ago = now() - timedelta(hours=1)
    no_problem = get_test_sms(
        True, send_results=str({'message_uid': 'blue'}),
        delivery_check_on=None, delivery_error=None, when_should=hour_ago)
    problem = get_test_sms(
        True, send_results=str({'message_uid': 'green'}),
        delivery_check_on=None, delivery_error=None, when_should=hour_ago,
        full_name='The Queen of Spain', phone='123-456-7890',
        sent_to='999-888-7777', message='Whats your fav color?')
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

    SMS.objects.verify_delivery(front=front, error_logger=error_logger)

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

    expected = [call(
        'SMS delivery errors',
        message,
        extra_to=settings.ALERT_BAD_PHONE,
        always_new_error=True)]
    self.assertEqual(error_logger.log_error.call_args_list, expected)

  def test_verify_emaildelivery(self):
    hour_ago = now() - timedelta(hours=1)
    no_problem = get_test_email(
        True, send_results=str({'_id': 'blue'}),
        delivery_check_on=None, delivery_error=None, when_should=hour_ago)
    problem = get_test_email(
        True, send_results=str({'_id': 'green'}),
        delivery_check_on=None, delivery_error=None, when_should=hour_ago,
        full_name='The Queen of Spain', email='new@mail.com',
        sent_to='old@mail.com', subject='Whats your fav color?')
    GuestyReservation.objects.create(
        reservation=problem.reservation, guesty_id='redblue')

    def delivery_error(_id):
      if _id == 'blue':
        return
      elif _id == 'green':
        return 'no_idea'
      raise Exception(_id)

    emailer = Mock(spec=Emailer)
    emailer.delivery_error.side_effect = delivery_error
    error_logger = Mock(spec=ErrorLogger)

    Email.objects.verify_delivery(emailer=emailer, error_logger=error_logger)

    no_problem.refresh_from_db()
    problem.refresh_from_db()
    self.assertIsNotNone(no_problem.delivery_check_on)
    self.assertIsNone(no_problem.delivery_error)
    self.assertIsNotNone(problem.delivery_check_on)
    self.assertEqual('no_idea', problem.delivery_error)

    message = (
        'The Queen of Spain\n'
        'https://app.guesty.com/reservations/redblue/guests\n'
        'sent to: old@mail.com\n'
        'note: the guest\'s email is now new@mail.com\n'
        'error: no_idea\n'
        'Whats your fav color?')

    expected = [call(
        'Email delivery errors',
        message,
        extra_to=settings.ALERT_BAD_PHONE,
        always_new_error=True)]
    self.assertEqual(error_logger.log_error.call_args_list, expected)
