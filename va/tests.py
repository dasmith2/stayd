from datetime import timedelta, date, time
from unittest.mock import Mock, call

from django.shortcuts import reverse
from djmoney.money import Money

from bgcheck.tests.test_background_check import get_test_background_check
from front.models import Front
from guest_messages.mandrill import Emailer
from guest_messages.mandrill_examples import SEND_RESULT
from guest_messages.models.email import Email
from guest_messages.models.message import (
    CC_ID_EVERYTHING_WRONG, GUEST_UPLOADED_NON_US_ID,
    GUEST_UPLOADED_US_ID_FRONT_ONLY, CHECKIN, DAYS, BEFORE,
    PAYMENT_DEPOSIT_ID_RECEIVED)
from guest_messages.models.sms import SMS
from guest_messages.tests import (
    get_test_smstemplate, get_test_emailtemplate, get_test_email)
from guesty.custom_field_ids import CHECKIN_INSTRUCTIONS_EMAIL
from id_verify.models import (
    PASSPORT, US_ID_FRONT_AND_BACK, US_ID_FRONT_ONLY, NON_US_ID)
from id_verify.tests import get_checkable_submission, get_test_submission
from reservations.syncer import GenericSyncer
from reservations.tests import get_test_reservation
from util.channels import BOOKINGCOM, AIRBNB
from util.tests import TestCase, get_test_user
from util.timezone import now, str_to_tz_dt
from util import twilio
from va.models import handle_checkin_instructions
from va.verify_id_ui import handle_id_verify_list_post_or_problem


class ViewTests(TestCase):
  def test_submissions(self):
    reservation = get_test_reservation(
        full_name='Bob Schmob', last_name='Schmob')
    sub = get_checkable_submission(reservation=reservation)

    not_in_id_verify = get_test_user(username='fatima')
    in_id_verify = get_test_user(username='bob', groups=['id_verify'])

    self.client.force_login(not_in_id_verify)
    self.assert_get_contains(
        reverse('submissions'),
        'You need to be in the id_verify or virtual_host group',
        assert_status=403)

    self.client.force_login(in_id_verify)

    self.assert_get_contains(reverse('submissions'), 'Is the ID valid?')
    self.assert_get_not_contains(reverse('escalated_submissions'), 'Schmob')

    # Escalate!
    self.client.get(reverse(
        'escalate_submission', kwargs={'submission_id': sub.pk}))
    self.assert_get_not_contains(reverse('submissions'), 'Is the ID valid?')
    self.assert_get_contains(reverse('escalated_submissions'), 'Schmob')


class PostTests(TestCase):
  """ Base class. No actual tests. """
  def setUp(self):
    super().setUp()
    self.reservation = get_test_reservation(
        check_in=now() + timedelta(days=2),
        check_out=now() + timedelta(days=4), channel=BOOKINGCOM,
        first_name='Bob', last_name='Blob', full_name='Bob Blob')
    self.submission = get_test_submission(
        channel=BOOKINGCOM, reservation=self.reservation)
    self.assertIsNone(self.submission.checked_at)
    self.assertIsNone(self.submission.checked_by)
    self.assertIsNone(self.submission.risk_score)
    self.assertIsNone(self.submission.id_matches_res)
    self.assertIsNone(self.submission.cc_matches_id)
    self.assertIsNone(self.submission.cc_matches_payment)


class BGCheckPostTests(PostTests):
  def setUp(self):
    super().setUp()
    self.reservation.rental.building.background_check_guests = True
    self.reservation.rental.building.save()
    self.bgcheck = get_test_background_check(reservation=self.reservation)
    self.post = {}
    self.post['submission_{}'.format(self.submission.pk)] = 'yep'
    self.post['{}_id_matches_res'.format(self.submission.pk)] = 'yes'
    self.post['{}_cc_matches_id'.format(self.submission.pk)] = 'yes'
    self.post['{}_cc_matches_payment'.format(self.submission.pk)] = 'yes'
    self.post['{}_birthday'.format(self.submission.pk)] = '1967-02-21'
    self.post['{}_legal_name'.format(self.submission.pk)] = 'Robert H Blob'
    self.post['{}_has_negative_reviews'.format(self.submission.pk)] = 'no'
    self.post['{}_positive_reviews'.format(self.submission.pk)] = '7'
    self.post['{}_booking_for_themself'.format(self.submission.pk)] = 'yes'
    self.post['{}_explained_trip'.format(self.submission.pk)] = 'yes'
    self.post['{}_lives_nearby'.format(self.submission.pk)] = 'no'
    self.type_key = '{}_id_type'.format(self.submission.pk)
    self.post[self.type_key] = PASSPORT
    self.front = Mock(spec=Front)
    self.syncer = Mock(spec=GenericSyncer)
    self.bob = get_test_user(email='bob@bob.blargh')
    self.has_is_voip = Mock(spec=twilio)
    self.has_is_voip.is_voip.return_value = False

  def test_must_cancel(self):
    self.bgcheck.passed = False
    self.bgcheck.started_at = now()
    self.bgcheck.completed_at = now()
    self.bgcheck.save()
    self.login(is_superuser=True)
    url = reverse('must_cancel')
    self.assert_get_contains(url, 'Bob Blob')

  def test_missing_birthday(self):
    self.post['{}_birthday'.format(self.submission.pk)] = ''
    problem = handle_id_verify_list_post_or_problem(
        self.post, self.bob, self.front, syncer=self.syncer)
    self.assertEqual(
        'I need to know when they were born for the background check', problem)
    self.submission.refresh_from_db()
    self.assertIsNone(self.submission.checked_at)

  def test_missing_legal_name(self):
    self.post['{}_legal_name'.format(self.submission.pk)] = ''
    problem = handle_id_verify_list_post_or_problem(
        self.post, self.bob, self.front, syncer=self.syncer)
    self.assertEqual((
        'I need to know their legal name from their ID for the '
        'background check'), problem)
    self.submission.refresh_from_db()
    self.assertIsNone(self.submission.checked_at)

  def test_invalid_option(self):
    self.post[self.type_key] = 'blargh'
    try:
      handle_id_verify_list_post_or_problem(
          self.post, self.bob, self.front, syncer=self.syncer)
      self.fail()
    except Exception:
      pass

  def test_missing_has_negative_reviews(self):
    self.post['{}_has_negative_reviews'.format(self.submission.pk)] = ''
    problem = handle_id_verify_list_post_or_problem(
        self.post, self.bob, self.front, syncer=self.syncer)
    self.assertEqual((
        'I need to know whether or not the guest has negative reviews for '
        'the risk score'), problem)
    self.submission.refresh_from_db()
    self.assertIsNone(self.submission.checked_at)

  def test_missing_positive_reviews(self):
    self.post['{}_positive_reviews'.format(self.submission.pk)] = ''
    problem = handle_id_verify_list_post_or_problem(
        self.post, self.bob, self.front, syncer=self.syncer)
    self.assertEqual(
        'I need to know the positive review count for the risk score', problem)
    self.submission.refresh_from_db()
    self.assertIsNone(self.submission.checked_at)

  def test_missing_booking_for_themself(self):
    self.post['{}_booking_for_themself'.format(self.submission.pk)] = ''
    problem = handle_id_verify_list_post_or_problem(
        self.post, self.bob, self.front, syncer=self.syncer)
    self.assertEqual((
        'I need to know whether or not the guest is booking for themself\'s '
        'for the risk score'), problem)
    self.submission.refresh_from_db()
    self.assertIsNone(self.submission.checked_at)

  def test_missing_explained_trip(self):
    self.post['{}_explained_trip'.format(self.submission.pk)] = ''
    problem = handle_id_verify_list_post_or_problem(
        self.post, self.bob, self.front, syncer=self.syncer)
    self.assertEqual((
        'I need to know whether or not the guest explained the reason for '
        'their trip for the risk score'), problem)
    self.submission.refresh_from_db()
    self.assertIsNone(self.submission.checked_at)

  def test_missing_lives_nearby(self):
    self.post['{}_lives_nearby'.format(self.submission.pk)] = ''
    problem = handle_id_verify_list_post_or_problem(
        self.post, self.bob, self.front, syncer=self.syncer)
    self.assertEqual((
        'I need to know whether or not the guest lives nearby for the risk '
        'score'), problem)
    self.submission.refresh_from_db()
    self.assertIsNone(self.submission.checked_at)

  def test_valid_passport(self):
    self.post[self.type_key] = PASSPORT
    handle_id_verify_list_post_or_problem(
        self.post, self.bob, self.front, syncer=self.syncer,
        has_is_voip=self.has_is_voip)
    self.submission.refresh_from_db()
    self.assertEqual(PASSPORT, self.submission.id_type)
    self.submission.refresh_from_db()
    self.assertTrue(self.submission.all_good())
    self.assertTrue(self.submission.reservation.id_verified)
    self.assertEqual(0, SMS.objects.count())
    self.assertEqual(date(1967, 2, 21), self.submission.birthday)
    self.assertEqual('Robert H Blob', self.submission.legal_name)

    self.assertFalse(self.submission.has_negative_reviews)
    self.assertEqual(7, self.submission.positive_reviews)
    self.assertTrue(self.submission.booking_for_themself)
    self.assertTrue(self.submission.explained_trip)
    self.assertFalse(self.submission.lives_nearby)

  def test_valid_us_id(self):
    self.post[self.type_key] = US_ID_FRONT_AND_BACK
    self.assertFalse(handle_id_verify_list_post_or_problem(
        self.post, self.bob, self.front, syncer=self.syncer,
        has_is_voip=self.has_is_voip))
    self.submission.refresh_from_db()
    self.assertEqual(US_ID_FRONT_AND_BACK, self.submission.id_type)
    self.submission.refresh_from_db()
    self.assertTrue(self.submission.all_good())
    self.assertEqual(0, SMS.objects.count())

  def test_us_id_only_front(self):
    get_test_smstemplate(
        triggering_event=GUEST_UPLOADED_US_ID_FRONT_ONLY,
        guesty_custom_field_id=None)

    self.post[self.type_key] = US_ID_FRONT_ONLY
    handle_id_verify_list_post_or_problem(
        self.post, self.bob, self.front, syncer=self.syncer)
    self.submission.refresh_from_db()
    self.assertFalse(self.submission.all_good())
    SMS.objects.get(
        reservation=self.reservation,
        template__triggering_event=GUEST_UPLOADED_US_ID_FRONT_ONLY)

  def test_non_us_id(self):
    get_test_smstemplate(
        triggering_event=GUEST_UPLOADED_NON_US_ID,
        guesty_custom_field_id=None)

    self.post[self.type_key] = NON_US_ID
    handle_id_verify_list_post_or_problem(
        self.post, self.bob, self.front, syncer=self.syncer)
    self.submission.refresh_from_db()
    self.assertFalse(self.submission.all_good())
    SMS.objects.get(
        reservation=self.reservation,
        template__triggering_event=GUEST_UPLOADED_NON_US_ID)


class VerifyListPostTests(PostTests):
  def test_handle_id_verify_list_post_ok(self):
    post = {}
    post['submission_{}'.format(self.submission.pk)] = 'yep'
    post['{}_id_matches_res'.format(self.submission.pk)] = 'yes'
    post['{}_cc_matches_id'.format(self.submission.pk)] = 'yes'
    post['{}_cc_matches_payment'.format(self.submission.pk)] = 'yes'
    post['{}_birthday'.format(self.submission.pk)] = '1967-02-21'
    post['{}_has_negative_reviews'.format(self.submission.pk)] = 'no'
    post['{}_positive_reviews'.format(self.submission.pk)] = '7'
    post['{}_booking_for_themself'.format(self.submission.pk)] = 'yes'
    post['{}_explained_trip'.format(self.submission.pk)] = 'yes'
    post['{}_lives_nearby'.format(self.submission.pk)] = 'no'

    front = Mock(spec=Front)
    syncer = Mock(spec=GenericSyncer)
    bob = get_test_user(email='bob@bob.blargh')
    has_is_voip = Mock(spec=twilio)
    has_is_voip.is_voip.return_value = False

    handle_id_verify_list_post_or_problem(
        post, bob, front, syncer=syncer, has_is_voip=has_is_voip)

    self.submission.refresh_from_db()
    self.assertIsNotNone(self.submission.checked_at)
    self.assertEqual(bob, self.submission.checked_by)
    self.assertTrue(self.submission.id_matches_res)
    self.assertTrue(self.submission.cc_matches_id)
    self.assertTrue(self.submission.cc_matches_payment)

    self.assertEqual(
        0, SMS.objects.filter(reservation=self.reservation).count())
    self.reservation.refresh_from_db()
    self.assertIsNone(
        self.reservation.riskscore.explain_why_cant_calculate_score())
    self.assertEqual(
        [call(self.reservation)], syncer.set_id_verified.call_args_list)
    # I don't really care that the correct score gets pushed here. I'm just
    # making sure that the risk score gets calculated and pushed. In terms of
    # an accurate score, see id_verify/tests/test_risk_score.py
    self.assertEqual(1, len(syncer.set_risk_score.call_args_list))
    self.assertEqual(
        self.reservation, syncer.set_risk_score.call_args_list[0][0][0])

  def test_handle_id_verify_list_post_not_ok(self):
    get_test_smstemplate(
        triggering_event=CC_ID_EVERYTHING_WRONG,
        guesty_custom_field_id=None)

    post = {}
    post['submission_{}'.format(self.submission.pk)] = 'yep'
    post['{}_id_matches_res'.format(self.submission.pk)] = 'no'
    post['{}_cc_matches_id'.format(self.submission.pk)] = 'no'
    post['{}_cc_matches_payment'.format(self.submission.pk)] = 'no'

    front = Mock(spec=Front)
    syncer = Mock(spec=GenericSyncer)
    bob = get_test_user(email='bob@bob.blargh')
    self.assertFalse(handle_id_verify_list_post_or_problem(
        post, bob, front, syncer=syncer))

    self.submission.refresh_from_db()
    self.assertIsNotNone(self.submission.checked_at)
    self.assertEqual(bob, self.submission.checked_by)
    self.assertFalse(self.submission.id_matches_res)
    self.assertFalse(self.submission.cc_matches_id)
    self.assertFalse(self.submission.cc_matches_payment)

    syncer.set_id_verified.assert_not_called()
    message = SMS.objects.get(reservation=self.reservation)
    self.assertEqual(
        message.template.triggering_event, CC_ID_EVERYTHING_WRONG)
    self.assertFalse(message.explain_why_do_not_send())


class HandleCheckinInstructionsTests(TestCase):
  def setUp(self):
    super().setUp()
    self.template = get_test_emailtemplate(
        subject='Checkin instructions',
        guesty_custom_field_id=CHECKIN_INSTRUCTIONS_EMAIL,
        triggering_event=None, pre_scheduled=True, preschedule_around=CHECKIN,
        offset=2, days_or_hours=DAYS, before_or_after=BEFORE,
        at_time=time(12, 0), check_before_sending=PAYMENT_DEPOSIT_ID_RECEIVED,
        allowed_hours_late=72)
    self.emailer = Mock(spec=Emailer)
    self.emailer.send_email.return_value = SEND_RESULT
    self.reservation = get_test_reservation(
        channel=AIRBNB,
        booked_at=str_to_tz_dt('2018-12-01 12:00'),
        check_in=str_to_tz_dt('2018-12-25 16:00'),
        check_out=str_to_tz_dt('2018-12-26 11:00'),
        ideal_payin=Money(100, 'USD'), actual_payin=Money(100, 'USD'),
        id_verified=True)
    self.email = get_test_email(
        template=self.template, send_results=None,
        reservation=self.reservation,
        when_should=str_to_tz_dt('2018-12-23 12:00'), when_did=None)
    self.assertFalse(self.email.explain_why_do_not_send())
    self.send_post = {'manually_send_checkin_instructions': (
        'Manually send checkin instructions')}

  def test_resend(self):
    self.email.when_did = str_to_tz_dt('2018-12-23 12:00')
    self.email.save()

    got = handle_checkin_instructions(
        self.reservation, None, is_superuser=False)
    self.assertEqual(
        'Sent Dec. 23, 2018, noon (NYC time)',
        got['checkin_instructions_sent'])
    self.assertFalse(got['why_not_auto_send_checkin_instructions'])
    self.assertFalse(got['id_not_verified'])
    self.assertFalse(got['send_checkin_instructions_problem'])
    self.assertFalse(got['why_cant_manually_send_checkin_instructions'])

    self.send_post['manual_email'] = 'manual@override.com'
    got2 = handle_checkin_instructions(
        self.reservation, self.send_post, is_superuser=False,
        emailer=self.emailer)
    self.assertEqual(
        'manual@override.com', self.emailer.send_email.call_args_list[0][0][1])
    self.assertEqual(2, Email.objects.filter(when_did__isnull=False).count())
    self.assertEqual('Sending...', got2['checkin_instructions_sent'])
    self.assertFalse(got2['why_not_auto_send_checkin_instructions'])
    self.assertFalse(got2['id_not_verified'])
    self.assertFalse(got2['send_checkin_instructions_problem'])
    self.assertEqual(
        'I\'m trying to send them as we speak',
        got2['why_cant_manually_send_checkin_instructions'])

  def test_id_not_verified_normal_va(self):
    self.reservation.id_verified = False
    self.reservation.save()
    got = handle_checkin_instructions(
        self.reservation, None, is_superuser=False)
    self.assertEqual(
        'Unsent. Scheduled for Dec. 23, 2018, noon (NYC time)',
        got['checkin_instructions_sent'])
    self.assertEqual(
        'the ID isn\'t verified',
        got['why_not_auto_send_checkin_instructions'])
    self.assertTrue(got['id_not_verified'])
    self.assertEqual(
        'the ID isn\'t verified',
        got['why_cant_manually_send_checkin_instructions'])

    got2 = handle_checkin_instructions(
        self.reservation, self.send_post, is_superuser=False)
    self.assertEqual((
        'I didn\'t just send the checkin instructions because the ID isn\'t '
        'verified'), got2['send_checkin_instructions_problem'])
    self.email.refresh_from_db()
    self.assertFalse(self.email.when_did)

  def test_id_not_verified_superuser(self):
    self.reservation.id_verified = False
    self.reservation.save()
    got = handle_checkin_instructions(
        self.reservation, None, is_superuser=True)
    self.assertEqual(
        'Unsent. Scheduled for Dec. 23, 2018, noon (NYC time)',
        got['checkin_instructions_sent'])
    self.assertEqual(
        'the ID isn\'t verified',
        got['why_not_auto_send_checkin_instructions'])
    self.assertTrue(got['id_not_verified'])
    self.assertFalse(got['why_cant_manually_send_checkin_instructions'])

    got2 = handle_checkin_instructions(
        self.reservation, self.send_post, is_superuser=True,
        emailer=self.emailer)
    self.assertEqual(1, Email.objects.count())
    self.assertFalse(got2['send_checkin_instructions_problem'])
    self.email.refresh_from_db()
    self.assertTrue(self.email.when_did)

    # Now let's say there's a delay in sending the email so it didn't actually
    # go out yet
    self.assertTrue(self.email.about_to_send)
    self.email.when_did = None
    self.email.save()

    # Then they resubmit the form for some reason!
    got3 = handle_checkin_instructions(
        self.reservation, self.send_post, is_superuser=True,
        emailer=self.emailer)
    self.assertEqual(1, Email.objects.count())
    self.assertEqual((
        'I didn\'t just send the checkin instructions because I\'m trying to '
        'send them as we speak'), got3['send_checkin_instructions_problem'])
