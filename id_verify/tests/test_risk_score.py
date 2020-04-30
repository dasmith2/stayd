from datetime import date
from unittest.mock import Mock, call

from django.conf import settings
from djmoney.money import Money

from errors.models import Notifier
from id_verify.models.risk_score import (
    ScoreFactor, high_risk_reservations_for_vas, high_risk_reservations_table)
from id_verify.tests import get_checkable_submission
from reservations.syncer import GenericSyncer
from reservations.tests import get_test_reservation
from util.channels import AIRBNB, BOOKINGCOM
from util.permission import VIRTUAL_HOST_GROUP
from util.tests import TestCase, get_test_user
from util.table import Cell, Row
from util.timezone import str_to_tz_dt
from util import twilio


def risk_score_user():
  return get_test_user(
      username='bob', email='bob@bob.blargh', groups=[VIRTUAL_HOST_GROUP])


class CreateRiskScoreTests(TestCase):
  def test_create_risk_score(self):
    self.assertIsNotNone(get_test_reservation().riskscore_or_none)


class SubmissionRiskScoreTests(TestCase):
  def test_valid_submission(self):
    submission = get_checkable_submission(
        birthday=date(2000, 1, 1), id_matches_res=True,
        checked_at=str_to_tz_dt('2018-01-01'), checked_by=risk_score_user())
    self.assertTrue(submission.all_good())
    self.assertEqual(20, submission.reservation.riskscore.years_old(
        nnow=str_to_tz_dt('2020-01-01')))


def no_risk_submission(has_is_voip):
  reservation = get_test_reservation(
      booked_at='2019-12-01 16:00', check_in='2019-12-11 16:00',
      check_out='2019-12-25 11:00', channel=AIRBNB,
      phone_number='555-5555-5555', guest_count=1, full_name='Good Gale')
  return get_checkable_submission(
      reservation=reservation, id_matches_res=True,
      has_is_voip=has_is_voip, birthday=date(1981, 11, 4),
      has_negative_reviews=False, booking_for_themself=True,
      explained_trip=True, positive_reviews=20,
      checked_at=str_to_tz_dt('2019-12-01'), lives_nearby=False,
      checked_by=risk_score_user())


def high_risk_submission(has_is_voip, reservation=None):
  """ This gets used in web tests and unit tests. """
  if not reservation:
    reservation = get_test_reservation(
        nickname='Daves Donut Shop',
        booked_at='2019-12-27 12:00', check_in='2019-12-27 16:00',
        check_out='2019-12-28 11:00', channel=BOOKINGCOM,
        full_name='James Avery', phone_number='555-5555-5555', guest_count=6,
        channel_id='verybadid', guesty_id='5cea',
        actual_payin=Money('100', 'USD'))
  return get_checkable_submission(
      reservation=reservation, id_matches_res=True, cc_matches_id=True,
      cc_matches_payment=True, has_is_voip=has_is_voip,
      birthday=date(2000, 1, 1), has_negative_reviews=True,
      booking_for_themself=False, explained_trip=False, positive_reviews=0,
      lives_nearby=True, checked_at=str_to_tz_dt('2019-12-01'),
      checked_by=risk_score_user(),
      resized_at=str_to_tz_dt('2019-12-01'))


class StartWithGoodRiskTests(TestCase):
  def setUp(self):
    super().setUp()
    self.has_is_voip = Mock(spec=twilio)
    self.has_is_voip.is_voip.return_value = False
    self.submission = no_risk_submission(self.has_is_voip)
    self.reservation = self.submission.reservation
    self.assertTrue(self.submission.all_good())
    self.assertFalse(self.reservation.riskscore.is_voip)

  def test_notify(self):
    self.reservation.booked_at = str_to_tz_dt('2019-12-07 16:00')
    self.reservation.save()
    self.submission.lives_nearby = True
    self.submission.positive_reviews = 0
    notifier = Mock(spec=Notifier)
    syncer = Mock(spec=GenericSyncer)
    for i in range(2):
      self.submission.save(
          has_is_voip=self.has_is_voip, notifier=notifier, syncer=syncer)
    self.reservation.refresh_from_db()
    self.assertEqual(85, self.reservation.riskscore.pushed_score)
    self.assertTrue(self.reservation.riskscore.notified_of_high_risk_at)
    to = settings.ALERT_HIGH_RISK_RESERVATION
    subject = 'Alert: Good Gale is a high risk reservation'
    message = (
        '{}\n\nThe guest has 0 positive reviews: 10\n'
        'The guest lives nearby: 75\n\nTotal risk score: 85').format(
            self.reservation.keys_url())
    self.assertEqual(
        [call(to, subject, message)], notifier.notify.call_args_list)

  def test_good_factors(self):
    factors = self.reservation.riskscore.score_factors()
    expected = [
        ScoreFactor(-10, 'The guest has 20 positive reviews'),
        ScoreFactor(-5, 'Booked 10 days in advance')]
    self.assertEqual(expected, factors)
    self.assertEqual(-15, self.reservation.riskscore.pushed_score)


class HighRiskReservationsTableTests(TestCase):
  def setUp(self):
    super().setUp()
    has_is_voip = Mock(spec=twilio)
    has_is_voip.is_voip.return_value = True
    self.high_risk = high_risk_submission(has_is_voip).reservation
    has_is_voip.is_voip.return_value = True
    no_risk_submission(has_is_voip).reservation

  def test_high_risk_reservations_table(self):
    table = high_risk_reservations_table([self.high_risk])
    self.assertEqual(1, len(table.rows))

    self.assertEqual([
        'Action', 'Guesty', 'Keys', 'Guest', 'Risk score', 'Factors',
        'Paid in so far', 'Check in', 'Channel'], table.headers)
    approve_button = (
        '<button type="submit" name="reservation_id" value="{}">'
        'Approve</button>').format(self.high_risk.pk)
    action = Cell(html_content=approve_button)
    guesty = Cell('guesty', url=self.high_risk.admin_url())
    keys = Cell('keys', url=self.high_risk.res_deets_url_no_server())
    guest = 'James Avery'
    risk_score = 1350
    factors = table.rows[0].cells[5]  # Cheating a bit here.
    paid_in = Money('100', 'USD')
    check_in = str_to_tz_dt('2019-12-27 16:00')
    channel = BOOKINGCOM
    expected_row = Row([
        action, guesty, keys, guest, risk_score, factors, paid_in, check_in,
        channel])

    table.rows[0].assertEqual(expected_row)

  def test_high_risk_reservations_for_vas(self):
    self.assertEqual([self.high_risk], list(high_risk_reservations_for_vas()))
    risk_score = self.high_risk.riskscore
    risk_score.reservation_approved_by = risk_score_user()
    risk_score.reservation_approved_at = str_to_tz_dt('2018-12-25')
    risk_score.save()
    self.assertEqual([], list(high_risk_reservations_for_vas()))


class AllBadRiskTests(TestCase):
  def test_bad_factors(self):
    has_is_voip = Mock(spec=twilio)
    has_is_voip.is_voip.return_value = True
    submission = high_risk_submission(has_is_voip)
    reservation = submission.reservation
    self.assertTrue(reservation.riskscore.is_voip)
    self.assertTrue(submission.all_good())

    factors = reservation.riskscore.score_factors(
        nnow=str_to_tz_dt('2019-12-25'))
    expected = [
        ScoreFactor(5, 'The channel is Booking.com'),
        ScoreFactor(100, 'The guest has negative reviews'),
        ScoreFactor(
            10, 'The person who booked isn\'t the person who\'s staying'),
        ScoreFactor(
            10, 'The guest didn\'t explain the purpose of their trip'),
        ScoreFactor(10, 'The guest has 0 positive reviews'),
        ScoreFactor(40, 'The guest has a VOIP phone number'),
        ScoreFactor(40, 'The guest is only 19 years old at checkin'),
        ScoreFactor(75, 'The guest lives nearby'),
        ScoreFactor(10, 'This reservation has 6 guests'),
        ScoreFactor(15, 'The reservation is only 1 nights long'),
        ScoreFactor(20, 'The reservation starts on a Friday'),
        ScoreFactor(15, 'Same day reservation'),
        ScoreFactor(1000, 'James Avery is blacklisted')]
    self.assertEqual(expected, factors)
    # 1350 = 5 + 100 + 10 + 10 + 10 + 40 + 40 + 75 + 10 + 15 + 20 + 15 + 1000
    self.assertEqual(1350, reservation.riskscore.pushed_score)
