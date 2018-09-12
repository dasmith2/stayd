from datetime import timedelta
from unittest.mock import Mock, call

from util.tests import TestCase
from django.utils.dateparse import parse_datetime

from errors.models import ErrorLogger
from guests.tests import get_test_guest
from guest_messages.models.front_contact_updater import FrontContactUpdater
from rentals.tests import get_test_rental
from reservations.tests import get_test_reservation
from util.clock import Clock
from front.models import (
    Front, ContactInfo, EMAIL, PHONE, BadContactInfoException)


class FrontContactUpdaterTests(TestCase):
  def test_alert_bad_number(self):
    front = Mock(speck=Front)
    front.set_contact_info.side_effect = BadContactInfoException(
        PHONE, 'test input', 'test output')
    error_logger = Mock(speck=ErrorLogger)
    front_contact_updater = FrontContactUpdater(
        front=front, error_logger=error_logger)
    reservation = get_test_reservation(
        True, phone='555-444-3322', guesty_id='whatever')

    for i in range(2):
      front_contact_updater.update_for_reservation_or_alert(reservation)

    self.assertEqual(1, len(error_logger.log_error.call_args_list))
    log_error_call = error_logger.log_error.call_args_list[0]
    call_args, call_kwargs = log_error_call[0], log_error_call[1]  # noqa:F841
    log_error_subject = call_args[0]
    self.assertEqual(
        'Bad phone number probably: 555-444-3322', log_error_subject)

  def test_alert_bad_email(self):
    front = Mock(speck=Front)
    front.set_contact_info.side_effect = BadContactInfoException(
        EMAIL, 'test input', 'test output')
    error_logger = Mock(speck=ErrorLogger)
    front_contact_updater = FrontContactUpdater(
        front=front, error_logger=error_logger)
    reservation = get_test_reservation(
        True, email='invalid_email_here', guesty_id='whatever')

    for i in range(2):
      front_contact_updater.update_for_reservation_or_alert(reservation)

    self.assertEqual(1, len(error_logger.log_error.call_args_list))
    log_error_call = error_logger.log_error.call_args_list[0]
    call_args, call_kwargs = log_error_call[0], log_error_call[1]  # noqa:F841
    log_error_subject = call_args[0]
    self.assertEqual(
        'Bad email address probably: invalid_email_here', log_error_subject)

  def test_update(self):
    now = parse_datetime('2018-05-29T16:00:00+00:00')

    guest = get_test_guest(
        True,
        full_name='The Queen of England',
        phone='123-456-7890',
        email='blargh@gmail.com')
    rental = get_test_rental(
        True,
        nickname='Buckingham')
    get_test_reservation(
        True,
        guest=guest,
        check_in=now,
        check_out=now + timedelta(days=1),
        rental=rental,
        guesty_id='helloworld')
    get_test_reservation(
        True,
        guest=guest,
        check_in=now + timedelta(days=1),
        check_out=now + timedelta(days=2),
        rental=rental,
        guesty_id='hellomars')

    mock_front = Mock(spec=Front)
    mock_clock = Mock(spec=Clock)
    mock_clock.now.return_value = now
    updater = FrontContactUpdater(mock_front, clock=mock_clock)

    updater._update_for_guest(guest)
    expected_info_1 = ContactInfo(
        'The Queen of England Buckingham',
        'checkin: 2018-05-29 11:00\ncheckout: 2018-05-30 11:00\ncity: Bismund',
        'https://app.guesty.com/reservations/helloworld/guests',
        '123-456-7890',
        'blargh@gmail.com')
    self.assertEqual(
        mock_front.set_contact_info.call_args_list, [call(expected_info_1)])

    guest.full_name = 'The King of France'
    guest.save()
    updater._update_for_guest(guest)
    expected_info_2 = ContactInfo(
        'The King of France Buckingham',
        'checkin: 2018-05-29 11:00\ncheckout: 2018-05-30 11:00\ncity: Bismund',
        'https://app.guesty.com/reservations/helloworld/guests',
        '123-456-7890',
        'blargh@gmail.com')
    self.assertEqual(
        mock_front.set_contact_info.call_args_list[1],
        call(expected_info_2))
