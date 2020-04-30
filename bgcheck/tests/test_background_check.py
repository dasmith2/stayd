from datetime import date, timedelta
from unittest.mock import Mock, call

from django.conf import settings
from django.shortcuts import reverse

from bgcheck.models.background_check import (
    door_person_table, DoorPerson, BackgroundCheck, BackgroundCheckAggregate,
    TimeToCompleteCheck,
    must_cancel_reservations, must_cancel_reservations_table,
    must_cancel_daily_notification_background,
    bgchecks_for_vas, bgcheck_reservations_table,
    bgcheck_required_daily_notification_background,
    post_save_background_check, BEEN_VERIFIED, check_for_run_out_of_time,
    post_sync_reservation)
from errors.models import Notifier
from guests.tests import get_test_guest
from id_verify.models import PASSPORT, consent_to_bgcheck_paragraph
from id_verify.tests import get_checkable_submission, get_test_submission
from rentals.tests import get_test_building, get_test_rental
from reservations.models.money import Reservation
from reservations.models.reservation_base import CANCELED
from reservations.tests import get_test_reservation
from util.channels import AIRBNB
from util.signals import post_sync
from util.table import Cell
from util.tests import TestCase, get_test_user
from util.timezone import str_to_tz_dt, now
from util.urls import keys_reverse, nnow_query


def get_test_door_person(**kwargs):
  user = kwargs.get('user', None)
  if not user:
    user = get_test_user(**kwargs)
  building = kwargs.get('building', None)
  if not building:
    building = get_test_building(**kwargs)
  return DoorPerson.objects.create(user=user, building=building)


def get_test_background_check(**kwargs):
  reservation = kwargs.get('reservation', None)
  if 'reservation' not in kwargs:
    reservation = get_test_reservation(**kwargs)
  submission = kwargs.get('submission', None)
  if not submission:
    submission = get_test_submission(
        reservation=reservation, birthday=date(1981, 11, 4),
        legal_name='full name here')
  bgcheck = BackgroundCheck.objects.create(
      reservation=reservation,
      submission=submission,
      provider=kwargs.get('provider', None),
      passed=kwargs.get('passed', None),
      got_valid_submission_at=kwargs.get('got_valid_submission_at', None),
      completed_at=kwargs.get('completed_at', None),
      not_completed_in_time=kwargs.get('not_completed_in_time', False),
      time_to_complete_saved=kwargs.get('time_to_complete_saved', False))
  if 'created_at' in kwargs:
    BackgroundCheck.objects.filter(pk=bgcheck.pk).update(
        created_at=kwargs['created_at'])
    bgcheck.refresh_from_db()
  return bgcheck


class BgCheckTests(TestCase):
  """ This is a base class. Don't put any actual tests in here. """
  def setUp(self):
    super().setUp()
    self.building = get_test_building(
        background_check_guests=True, nickname='Blarghs Hidey Hole',
        city='Excitingtown')
    rental = get_test_rental(
        building=self.building, nickname='Steves place #2')
    self.guest = get_test_guest(
        full_name='Davery Doo', first_name='Davery', last_name='Doo',
        email='davery@doo.dave')
    self.reservation = get_test_reservation(
        rental=rental, booked_at=str_to_tz_dt('2018-12-20 12:00'),
        check_in=str_to_tz_dt('2018-12-25 16:00'),
        check_out=str_to_tz_dt('2018-12-26 11:00'), guest=self.guest,
        channel_id='QWERTY1', channel=AIRBNB, guesty_id='foobily')
    post_sync.send(
        sender=Reservation, instance=self.reservation,
        nnow=str_to_tz_dt('2018-12-20 12:00'))
    self.assertIsNotNone(self.reservation.backgroundcheck_or_none)
    self.check = self.reservation.backgroundcheck
    BackgroundCheck.objects.filter(pk=self.check.pk).update(
        created_at=str_to_tz_dt('2018-12-21 12:00'))
    self.check.refresh_from_db()


class SubmissionTests(BgCheckTests):
  """ Base class. Don't put any actual tests in here. """
  def setUp(self):
    super().setUp()
    self.assertIsNone(self.check.got_valid_submission_at)
    self.submission = get_checkable_submission(
        reservation=self.reservation, id_matches_res=True,
        birthday=date(1957, 2, 20), legal_name='full name here',
        id_type=PASSPORT, id_file_name='davery_id.jpg',
        checked_at=str_to_tz_dt('2018-12-24 12:00'),
        checked_by=get_test_user())
    self.assertTrue(self.submission.all_good())
    self.check.refresh_from_db()
    self.assertTrue(
        self.check.got_valid_submission_at > now() - timedelta(minutes=1))
    self.assertEqual(self.submission, self.check.submission)


class SetBackgroundCheckTests(SubmissionTests):
  def test_second_submission(self):
    second_submission = get_checkable_submission(
        reservation=self.reservation, id_matches_res=True,
        birthday=date(1957, 2, 20), legal_name='full name here',
        id_type=PASSPORT, id_file_name='davery_id_2.jpg',
        checked_at=str_to_tz_dt('2018-12-24 13:00'),
        checked_by=get_test_user())
    self.assertTrue(second_submission.all_good())
    self.check.refresh_from_db()
    self.assertEqual(second_submission, self.check.submission)

  def test_second_invalid_submission(self):
    second_submission = get_checkable_submission(
        reservation=self.reservation, id_matches_res=False,
        birthday=date(1957, 2, 20), legal_name='full name here',
        id_type=PASSPORT, id_file_name='davery_id_2.jpg')
    self.assertFalse(second_submission.all_good())
    self.check.refresh_from_db()
    self.assertEqual(self.submission, self.check.submission)


class CheckForRunOutOfTimeTests(BgCheckTests):
  def test_check_for_run_out_of_time(self):
    # check_in=str_to_tz_dt('2018-12-25 16:00')
    check_for_run_out_of_time(nnow=str_to_tz_dt('2018-12-25 09:59'))
    self.assertFalse(BackgroundCheck.objects.filter(
        not_completed_in_time=True).exists())

    check_for_run_out_of_time(nnow=str_to_tz_dt('2018-12-25 10:00'))
    self.check.refresh_from_db()
    self.assertTrue(self.check.not_completed_in_time)


class CanDiscardTests(BgCheckTests):
  def test_can_discard_failed(self):
    self.check.passed = False
    self.check.got_valid_submission_at = str_to_tz_dt('2018-12-23')
    self.check.completed_at = str_to_tz_dt('2018-12-24 12:00')
    self.check.save()
    self.assertFalse(self.check.can_discard(
        nnow=str_to_tz_dt('2018-12-24 12:00') + timedelta(days=59, hours=23)))
    self.assertTrue(self.check.can_discard(
        nnow=str_to_tz_dt('2018-12-24 12:00') + timedelta(days=60)))

  def test_can_discard_passed(self):
    self.check.passed = True
    self.check.got_valid_submission_at = str_to_tz_dt('2018-12-23')
    self.check.completed_at = str_to_tz_dt('2018-12-24 12:00')
    self.check.save()
    self.assertFalse(self.check.can_discard(
        nnow=str_to_tz_dt('2018-12-26 23:59')))
    self.assertTrue(self.check.can_discard(
        nnow=str_to_tz_dt('2018-12-27 00:00')))

  def test_can_discard_opt_out(self):
    self.check.submission = get_test_submission(
        opt_out_of_bgcheck=True, reservation=self.reservation)
    self.check.save()
    self.assertFalse(self.check.can_discard(
        nnow=str_to_tz_dt('2018-12-26 23:59')))
    self.assertTrue(self.check.can_discard(
        nnow=str_to_tz_dt('2018-12-27 00:00')))

    self.reservation.status = CANCELED
    self.reservation.canceled_at = str_to_tz_dt('2018-12-21')
    self.reservation.save()
    self.check.refresh_from_db()
    self.assertTrue(self.check.can_discard(
        nnow=str_to_tz_dt('2018-12-21')))

  def test_can_discard_not_completed_in_time(self):
    self.check.not_completed_in_time = True
    self.check.save()
    self.assertFalse(self.check.can_discard())
    self.check.got_valid_submission_at = str_to_tz_dt('2018-12-23')
    self.check.completed_at = str_to_tz_dt('2019-02-01')
    self.assertTrue(self.check.can_discard())


class TimeToCompleteCheckTests(BgCheckTests):
  def test_complete(self):
    self.check.refresh_from_db()
    self.check.got_valid_submission_at = str_to_tz_dt('2018-12-20 12:00')
    self.check.completed_at = str_to_tz_dt('2018-12-21 12:00:01')
    self.check.passed = True
    self.check.save()
    self.check.refresh_from_db()
    self.assertTrue(self.check.time_to_complete_saved)
    TimeToCompleteCheck.objects.get(
        month=date(2018, 12, 1), seconds=24 * 60 * 60 + 1)


class AnonymizeOldTests(BgCheckTests):
  def test_anonymize_old_passes(self):
    self.check.passed = True
    self.check.got_valid_submission_at = str_to_tz_dt('2018-12-23')
    self.check.completed_at = str_to_tz_dt('2018-12-24')
    self.check.save()

    BackgroundCheck.objects.anonymize_old(
        nnow=str_to_tz_dt('2018-12-26 23:59'))
    self.assertFalse(BackgroundCheckAggregate.objects.exists())

    BackgroundCheck.objects.anonymize_old(
        nnow=str_to_tz_dt('2018-12-27 00:00'))
    self.assertFalse(BackgroundCheck.objects.exists())
    BackgroundCheckAggregate.objects.get(
        building=self.building, month=date(2018, 12, 1), passes=1,
        canceled_due_to_fail=0, opt_out=0, not_completed_in_time=0)

  def test_anonymize_old_canceled_due_to_fail(self):
    self.reservation.status = CANCELED
    self.reservation.canceled_at = str_to_tz_dt('2018-12-24 12:00')
    self.reservation.save()
    self.check.passed = False
    self.check.got_valid_submission_at = str_to_tz_dt('2018-12-23')
    self.check.completed_at = str_to_tz_dt('2018-12-24 12:00')
    self.check.save()
    BackgroundCheck.objects.anonymize_old(
        nnow=str_to_tz_dt('2018-12-24 12:00') + timedelta(days=60))
    BackgroundCheckAggregate.objects.get(
        building=self.building, month=date(2018, 12, 1), passes=0,
        canceled_due_to_fail=1, opt_out=0, not_completed_in_time=0)

  def test_anonymize_old_opt_out(self):
    self.check.submission = get_test_submission(
        opt_out_of_bgcheck=True, reservation=self.reservation)
    self.check.save()
    self.reservation.canceled_at = str_to_tz_dt('2018-12-22 12:00')
    self.reservation.status = CANCELED
    self.reservation.save()
    BackgroundCheck.objects.anonymize_old(
        nnow=str_to_tz_dt('2018-12-22 12:00'))
    BackgroundCheckAggregate.objects.get(
        building=self.building, month=date(2018, 12, 1), passes=0,
        canceled_due_to_fail=0, opt_out=1, not_completed_in_time=0)

  def test_anonymize_old_not_completed_in_time(self):
    self.check.not_completed_in_time = True
    self.check.got_valid_submission_at = str_to_tz_dt('2018-12-23')
    self.check.completed_at = str_to_tz_dt('2019-02-01')
    self.check.passed = True
    self.check.save()
    BackgroundCheck.objects.anonymize_old(nnow=str_to_tz_dt('2019-02-01'))
    BackgroundCheckAggregate.objects.get(
        building=self.building, month=date(2018, 12, 1), passes=1,
        canceled_due_to_fail=0, opt_out=0, not_completed_in_time=1)


class DoorPersonTests(BgCheckTests):
  def setUp(self):
    super().setUp()
    self.door_person = get_test_door_person(building=self.building)

  def test_reservations(self):
    get_test_reservation(  # Wrong building
        check_in=str_to_tz_dt('2018-12-25 16:00'),
        check_out=str_to_tz_dt('2018-12-26 11:00'))
    get_test_reservation(  # Too early
        building=self.building, check_in=str_to_tz_dt('2018-12-20 16:00'),
        check_out=str_to_tz_dt('2018-12-21 11:00'), guest=self.guest)

    reservations = self.door_person.reservations(
        nnow=str_to_tz_dt('2018-12-26 12:00'))
    self.assertEqual([self.reservation], list(reservations))

  def test_door_person_table(self):
    self.check.got_valid_submission_at = str_to_tz_dt('2018-12-23')
    self.check.completed_at = str_to_tz_dt('2018-12-24 12:00')
    self.check.passed = True
    self.check.save()
    reservations = self.door_person.reservations(
        nnow=str_to_tz_dt('2018-12-26 12:00'))
    table = door_person_table(reservations)
    expected_headers = [
        'Guest', 'Unit', 'Check in', 'Check out', 'Background check passed on']
    self.assertEqual(expected_headers, table.headers)
    self.assertEqual(1, len(table.rows))
    expected_cells = [
        'Davery Doo', 'Steves place #2', 'Dec. 25, 2018, 4 p.m.',
        'Dec. 26, 2018, 11 a.m.', 'Dec. 24, 2018']
    self.assertEqual(expected_cells, table.rows[0].cells)

    self.login(user=self.door_person.user)
    url = reverse('door_person') + nnow_query(date(2018, 12, 25))
    self.assert_get_contains(url, 'Davery Doo')


class GetAndSetCheckTests(BgCheckTests):
  def test_set_passed(self):
    self.check.got_valid_submission_at = str_to_tz_dt('2018-12-23')
    self.check.set_passed(True)
    self.assertTrue(self.check.passed)
    self.assertTrue(self.check.completed_at)
    self.assertEqual(BEEN_VERIFIED, self.check.provider)

  def test_bgchecks_for_vas_incomplete(self):
    self.assertEqual([self.reservation], list(
        bgchecks_for_vas(nnow=str_to_tz_dt('2018-12-25'))))

  def test_bgchecks_for_vas_post_checkout(self):
    self.assertEqual([], list(
        bgchecks_for_vas(nnow=str_to_tz_dt('2019-01-01'))))

  def test_bgchecks_for_vas_recently_complete(self):
    self.check.got_valid_submission_at = str_to_tz_dt('2018-12-23 13:00')
    self.check.passed = True
    self.check.completed_at = str_to_tz_dt('2018-12-24 12:00')
    self.check.save()
    self.assertEqual([self.reservation], list(
        bgchecks_for_vas(nnow=str_to_tz_dt('2018-12-24 12:59'))))
    self.assertEqual([], list(
        bgchecks_for_vas(nnow=str_to_tz_dt('2018-12-24 13:00'))))

  def _cells(self):
    guest_cell = Cell('Davery Doo', classes=['guest_name'])
    guesty_cell = Cell(
        'QWERTY1', url='https://app.guesty.com/reservations/foobily/guests')
    keys_cell = Cell(
        self.reservation.pk,
        url=reverse('va_reservation', kwargs={'pk': self.reservation.pk}))
    front = Cell(img_url=reverse(
        'view_sensitive_image', kwargs={'file_name': 'davery_id.jpg'}))
    back = Cell(img_url=reverse(
        'view_sensitive_image', kwargs={'file_name': 'davery_back_of_id.jpg'}))
    passed = Cell(None, classes=['passed'])
    mark_passed = (
        '<button data-id="{}" data-value="True" class="mark_passed">'
        'Passed</button>').format(self.check.pk)
    mark_not_passed = (
        '<button data-id="{}" data-value="False" class="mark_passed">'
        'Did not pass</button>').format(self.check.pk)
    return (
        guest_cell, guesty_cell, keys_cell, front, back, passed, mark_passed,
        mark_not_passed)

  def test_bgcheck_reservations_table_valid_submission(self):
    self.check.submission = get_checkable_submission(
        reservation=self.reservation, id_file_name='davery_id.jpg',
        id_back_file_name='davery_back_of_id.jpg', birthday=date(1981, 11, 4),
        legal_name='middle last')
    self.check.save()
    self.assertEqual([self.reservation], list(
        bgchecks_for_vas(nnow=str_to_tz_dt('2018-12-25'))))
    # nnow is currently accurate (aaaaand now it's off by 2 minutes). Also this
    # is my birthday, so that's how come I know it should say 37 years old
    # (barely).
    table = bgcheck_reservations_table(
        [self.reservation], nnow=str_to_tz_dt('2019-10-17 16:41'))
    self.assertEqual([
        'Guest', 'Age', 'Legal name', 'Check in', 'Guesty', 'Keys',
        'ID front', 'ID back', 'Passed', 'Mark passed',
        'Mark not passed', 'Explain why can\'t check', 'First appeared',
        'Became checkable'], table.headers)
    self.assertEqual(1, len(table.rows))

    (guest_cell, guesty_cell, keys_cell, front, back, passed, mark_passed,
        mark_not_passed) = self._cells()

    expected_row = [
        guest_cell, 37, 'middle last', date(2018, 12, 25), guesty_cell,
        keys_cell, front, back, passed, mark_passed, mark_not_passed, None,
        str_to_tz_dt('2018-12-21 12:00'), None]
    self.assertEqual(expected_row, table.rows[0].cells)

  def test_bgcheck_reservations_table_no_valid_submission(self):
    table = bgcheck_reservations_table(
        [self.reservation], nnow=str_to_tz_dt('2019-10-17 16:41'))
    self.assertFalse(self.reservation.id_verified)

    (guest_cell, guesty_cell, keys_cell, front, back, passed, mark_passed,
        mark_not_passed) = self._cells()

    mark_passed = None
    mark_not_passed = None

    expected_row = [
        guest_cell, None, None, date(2018, 12, 25), guesty_cell,
        keys_cell, mark_passed, mark_not_passed, passed, mark_passed,
        mark_not_passed, 'No valid submission',
        str_to_tz_dt('2018-12-21 12:00'), None]
    self.assertEqual(expected_row, table.rows[0].cells)

  def test_manual_id_verification(self):
    self.reservation.id_verified = True
    self.reservation.save()
    self.check.refresh_from_db()

    self.assertFalse(self.check.explain_why_cant_run_check())

    post_sync_reservation(
        Reservation, self.reservation, nnow=str_to_tz_dt('2018-12-25'))
    notifier = Mock(spec=Notifier)
    post_save_background_check(
        BackgroundCheck, self.check, notifier=notifier,
        nnow=str_to_tz_dt('2018-12-25'))
    self.assertEqual(1, len(notifier.notify.call_args_list))
    to, subject = notifier.notify.call_args_list[0][0]
    message = notifier.notify.call_args_list[0][1]['message']
    self.assertEqual(settings.ALERT_BGCHECK_REQUIRED, to)
    self.assertEqual((
        'A background check is required for Davery Doo\'s '
        'reservation'), subject)
    self.assertTrue(message.find(consent_to_bgcheck_paragraph()) >= 0)

  def test_bgcheck_daily_notification(self):
    notifier = Mock(spec=Notifier)
    bgcheck_required_daily_notification_background(
        notifier=notifier, nnow=str_to_tz_dt('2018-12-25'))
    subject = '1 reservation(s) require background checks'
    message = keys_reverse('bgcheck')
    expected = call(
        settings.ALERT_BGCHECK_REQUIRED, subject, message=message)
    self.assertEqual([expected], notifier.notify.call_args_list)


class MustCancelTests(BgCheckTests):
  def test_must_cancel_none(self):
    self.assertEqual([], list(
        must_cancel_reservations(nnow=str_to_tz_dt('2018-12-24'))))

  def test_must_cancel_opt_out(self):
    self.check.submission = get_test_submission(
        opt_out_of_bgcheck=True, reservation=self.reservation)
    self.check.save()
    self.assertEqual([self.reservation], list(
        must_cancel_reservations(nnow=str_to_tz_dt('2018-12-24'))))

    self.reservation.status = CANCELED
    self.reservation.canceled_at = str_to_tz_dt('2018-12-24')
    self.reservation.save()
    self.assertEqual([], list(
        must_cancel_reservations(nnow=str_to_tz_dt('2018-12-24'))))

  def test_must_cancel_failed(self):
    self.check.passed = False
    self.check.got_valid_submission_at = str_to_tz_dt('2018-12-23')
    self.check.completed_at = str_to_tz_dt('2018-12-24')
    self.check.save()
    self.assertEqual([self.reservation], list(
        must_cancel_reservations(nnow=str_to_tz_dt('2018-12-24'))))

  def test_must_cancel_not_complete_in_time(self):
    self.check.not_completed_in_time = True
    self.check.save()
    self.assertEqual([self.reservation], list(
        must_cancel_reservations(nnow=str_to_tz_dt('2018-12-24'))))

    # Guarantee this'll happen at some point. It didn't get canceled and
    # luckily it passed.
    self.check.passed = True
    self.check.got_valid_submission_at = str_to_tz_dt('2018-12-23')
    self.check.completed_at = str_to_tz_dt('2018-12-24 23:00')
    self.check.save()
    self.assertEqual([], list(
        must_cancel_reservations(nnow=str_to_tz_dt('2018-12-24'))))

  def test_must_cancel_reservations_table(self):
    self.check.passed = False
    self.check.got_valid_submission_at = str_to_tz_dt('2018-12-23')
    self.check.completed_at = str_to_tz_dt('2018-12-24 23:00')
    self.check.save()
    table = must_cancel_reservations_table([self.reservation])
    headers = [
        'Reservation in Guesty', 'Reservation in Keys', 'Guest', 'Check in',
        'Channel']
    self.assertEqual(headers, table.headers)
    self.assertEqual(1, len(table.rows))
    guesty_cell = Cell(
        'QWERTY1', url='https://app.guesty.com/reservations/foobily/guests')
    keys_cell = Cell(
        self.reservation.pk,
        url=reverse('va_reservation', kwargs={'pk': self.reservation.pk}))
    expected_row_cells = [
        guesty_cell, keys_cell, 'Davery Doo', str_to_tz_dt('2018-12-25 16:00'),
        AIRBNB]
    self.assertEqual(expected_row_cells, table.rows[0].cells)

  def test_must_cancel_immediate_notification(self):
    self.check.passed = False
    self.check.got_valid_submission_at = str_to_tz_dt('2018-12-23')
    self.check.completed_at = str_to_tz_dt('2018-12-24')
    self.check.save()
    notifier = Mock(spec=Notifier)
    post_save_background_check(
        BackgroundCheck, self.check, notifier=notifier,
        nnow=str_to_tz_dt('2018-12-25'))
    message = (
        'We are obligated to cancel this reservation and offer a full refund.'
        '\n\nDavery Doo\n'
        '(no longer) checking in on Dec. 25, 2018, 4 p.m.\n'
        'https://app.guesty.com/reservations/foobily/guests')
    expected = call(
        settings.ALERT_MUST_CANCEL,
        'Please cancel and refund Davery Doo\'s reservation', message=message)
    self.assertEqual([expected], notifier.notify.call_args_list)

  def test_must_cancel_daily_notification_none(self):
    notifier = Mock(spec=Notifier)
    must_cancel_daily_notification_background(
        notifier=notifier, nnow=str_to_tz_dt('2018-12-24'))
    self.assertEqual([], notifier.notify.call_args_list)

  def test_must_cancel_daily_notification(self):
    self.check.passed = False
    self.check.got_valid_submission_at = str_to_tz_dt('2018-12-23')
    self.check.completed_at = str_to_tz_dt('2018-12-24')
    self.check.save()
    notifier = Mock(spec=Notifier)
    must_cancel_daily_notification_background(
        notifier=notifier, nnow=str_to_tz_dt('2018-12-24'))
    subject = '1 reservation(s) must still be canceled and refunded'
    message = keys_reverse('must_cancel')
    expected = call(settings.ALERT_MUST_CANCEL, subject, message=message)
    self.assertEqual([expected], notifier.notify.call_args_list)
