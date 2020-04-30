from rentals.tests import get_test_rental
from work.models.maintenance_window import (
    gaps, maintenance_windows, Gap, MaintenanceWindow)
from reservations.tests import get_test_reservation
from util.tests import TestCase
from util.timezone import str_to_tz_dt


class InReservationTests(TestCase):
  def setUp(self):
    super().setUp()
    self.rental = get_test_rental()
    get_test_reservation(
        rental=self.rental,
        check_in=str_to_tz_dt('2018-12-20 16:00'),
        check_out=str_to_tz_dt('2018-12-30 11:00'))

  def test_in_reservation_gaps(self):
    got_gaps = gaps(self.rental, 3, nnow=str_to_tz_dt('2018-12-20 12:00'))
    expected_gaps = [Gap(
        str_to_tz_dt('2018-12-20 11:00'), str_to_tz_dt('2018-12-20 16:00'))]
    self.assertEqual(expected_gaps, got_gaps)

    got_gaps = gaps(self.rental, 3, nnow=str_to_tz_dt('2018-12-21 10:00'))
    self.assertEqual([], got_gaps)

  def test_middle_of_reservation_windows(self):
    got_windows = maintenance_windows(
        self.rental, 3, nnow=str_to_tz_dt('2018-12-20 12:00'))
    self.assertEqual([], got_windows)

    got_windows = maintenance_windows(
        self.rental, 3, nnow=str_to_tz_dt('2018-12-21 10:00'))
    self.assertEqual([], got_windows)


class NoReservationsTests(TestCase):
  def test_no_reservations_gaps_pre_check_out_time(self):
    got_gaps = gaps(
        get_test_rental(), 3, nnow=str_to_tz_dt('2018-12-20 10:00'))
    expected_gaps = [Gap(str_to_tz_dt('2018-12-20 11:00'), None)]
    self.assertEqual(expected_gaps, got_gaps)

  def test_no_reservations_gaps_past_check_out_time(self):
    got_gaps = gaps(
        get_test_rental(), 3, nnow=str_to_tz_dt('2018-12-20 12:00'))
    expected_gaps = [Gap(str_to_tz_dt('2018-12-20 11:00'), None)]
    self.assertEqual(expected_gaps, got_gaps)

  def test_no_reservations_windows_pre_check_out_time(self):
    # Between midnight and check out time on a vacant night, the upcoming
    # checkout time starts to count as immediately after a reservation for
    # scheduling purposes because you can't book a reservation for the night
    # you're in at 1am.
    got_windows = maintenance_windows(
        get_test_rental(), 2, nnow=str_to_tz_dt('2018-12-20 10:00'))
    expected_days = [
        MaintenanceWindow(str_to_tz_dt('2018-12-20 11:15'), True, None),
        MaintenanceWindow(str_to_tz_dt('2018-12-21 11:15'), False, None)]
    self.assertEqual(expected_days, got_windows)

  def test_no_reservations__past_check_out_timendows(self):
    # But once we've gone past check out time, up to midnight, somebody could
    # conceivably book for the night they're in.
    got_windows = maintenance_windows(
        get_test_rental(), 2, nnow=str_to_tz_dt('2018-12-20 12:00'))
    expected_days = [
        MaintenanceWindow(str_to_tz_dt('2018-12-21 11:15'), False, None),
        MaintenanceWindow(str_to_tz_dt('2018-12-22 11:15'), False, None)]
    self.assertEqual(expected_days, got_windows)


class GapTests(TestCase):
  def setUp(self):
    super().setUp()
    self.rental = get_test_rental()
    get_test_reservation(
        check_in=str_to_tz_dt('2018-12-20 16:00'),
        check_out=str_to_tz_dt('2018-12-22 11:00'), rental=self.rental)
    get_test_reservation(
        check_in=str_to_tz_dt('2018-12-22 16:00'),
        check_out=str_to_tz_dt('2018-12-23 11:00'), rental=self.rental)
    get_test_reservation(
        check_in=str_to_tz_dt('2018-12-26 16:00'),
        check_out=str_to_tz_dt('2018-12-27 11:00'), rental=self.rental)

  def test_gaps(self):
    got_gaps = gaps(self.rental, 10, nnow=str_to_tz_dt('2018-12-20 10:00'))
    _20_16 = str_to_tz_dt('2018-12-20 16:00')
    _22_16 = str_to_tz_dt('2018-12-22 16:00')
    _26_16 = str_to_tz_dt('2018-12-26 16:00')
    expected_gaps = [
        Gap(str_to_tz_dt('2018-12-20 11:00'), _20_16),
        Gap(str_to_tz_dt('2018-12-22 11:00'), _22_16),
        Gap(str_to_tz_dt('2018-12-23 11:00'), _26_16),
        Gap(str_to_tz_dt('2018-12-27 11:00'), None)]
    self.assertEqual(expected_gaps, got_gaps)

  def test_maintenance_windows(self):
    got_windows = maintenance_windows(
        self.rental, 9, nnow=str_to_tz_dt('2018-12-20 10:00'))

    # I know there isn't actually a check out on the 20th, but since it's
    # today, we consider this to satisfy any kind of "immediately after a
    # reservation" type requirement for scheduling.
    expected_0 = MaintenanceWindow(
        str_to_tz_dt('2018-12-20 11:15'), True,
        str_to_tz_dt('2018-12-20 16:00'))
    self.assertEqual(expected_0, got_windows[0])
    self.assertEqual(False, got_windows[0].is_vacant_night())
    self.assertEqual(True, got_windows[0].before_or_after_reservation())

    expected_1 = MaintenanceWindow(
        str_to_tz_dt('2018-12-22 11:15'), True,
        str_to_tz_dt('2018-12-22 16:00'))
    self.assertEqual(expected_1, got_windows[1])
    self.assertEqual(False, got_windows[1].is_vacant_night())
    self.assertEqual(True, got_windows[1].before_or_after_reservation())

    expected_2 = MaintenanceWindow(
        str_to_tz_dt('2018-12-23 11:15'), True,
        str_to_tz_dt('2018-12-26 16:00'))
    self.assertEqual(expected_2, got_windows[2])
    self.assertEqual(True, got_windows[2].is_vacant_night())
    self.assertEqual(True, got_windows[2].before_or_after_reservation())
    self.assertEqual(
        True, got_windows[2].vacant_night_before_or_after_reservation())

    expected_3 = MaintenanceWindow(
        str_to_tz_dt('2018-12-24 11:15'), False,
        str_to_tz_dt('2018-12-26 16:00'))
    self.assertEqual(expected_3, got_windows[3])
    self.assertEqual(True, got_windows[3].is_vacant_night())
    self.assertEqual(False, got_windows[3].before_or_after_reservation())
    self.assertEqual(
        False, got_windows[3].vacant_night_before_or_after_reservation())

    expected_4 = MaintenanceWindow(
        str_to_tz_dt('2018-12-25 11:15'), False,
        str_to_tz_dt('2018-12-26 16:00'))
    self.assertEqual(expected_4, got_windows[4])
    self.assertEqual(True, got_windows[4].is_vacant_night())
    self.assertEqual(False, got_windows[4].before_or_after_reservation())
    self.assertEqual(
        True, got_windows[4].vacant_night_before_or_after_reservation())

    expected_5 = MaintenanceWindow(
        str_to_tz_dt('2018-12-26 11:15'), False,
        str_to_tz_dt('2018-12-26 16:00'))
    self.assertEqual(expected_5, got_windows[5])
    self.assertEqual(False, got_windows[5].is_vacant_night())
    self.assertEqual(True, got_windows[5].before_or_after_reservation())

    expected_6 = MaintenanceWindow(
        str_to_tz_dt('2018-12-27 11:15'), True, None)
    self.assertEqual(expected_6, got_windows[6])
    self.assertEqual(True, got_windows[6].is_vacant_night())
    self.assertEqual(True, got_windows[6].before_or_after_reservation())
    self.assertEqual(
        True, got_windows[6].vacant_night_before_or_after_reservation())

    expected_7 = MaintenanceWindow(
        str_to_tz_dt('2018-12-28 11:15'), False, None)
    self.assertEqual(expected_7, got_windows[7])
    self.assertTrue(got_windows[7].is_vacant_night())
    self.assertFalse(got_windows[7].before_or_after_reservation())
    self.assertFalse(got_windows[7].vacant_night_before_or_after_reservation())

    self.assertEqual(8, len(got_windows))
