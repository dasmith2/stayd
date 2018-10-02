from datetime import timedelta
from unittest.mock import Mock, call

from util.tests import TestCase

from errors.models import Notifier
from guests.tests import get_test_guest
from guest_messages.models.front_contact_updater import FrontContactUpdater
from rentals.tests import get_test_rental
from reservations.tests import get_test_reservation
from util.clock import Clock
from util.timezone import str_to_tz_dt
from front.models import (
    Front, ContactInfo, EMAIL, PHONE, BadContactInfoException)


class FrontContactUpdaterTests(TestCase):
  def test_alert_bad_number(self):
    front = Mock(speck=Front)
    front.set_contact_info.side_effect = BadContactInfoException(
        PHONE, 'test input', 'test output')
    notifier = Mock(speck=Notifier)
    front_contact_updater = FrontContactUpdater(
        front=front, notifier=notifier)
    reservation = get_test_reservation(
        True, phone='555-444-3322', guesty_id='whatever')

    for i in range(2):
      front_contact_updater.update_for_reservation_or_alert(reservation)

    self.assertEqual(1, len(notifier.notify.call_args_list))
    notify_call = notifier.notify.call_args_list[0]
    call_args, call_kwargs = notify_call[0], notify_call[1]  # noqa:F841
    notify_subject = call_args[1]
    self.assertEqual(
        'Bad phone number probably: 555-444-3322', notify_subject)

  def test_alert_bad_email(self):
    front = Mock(speck=Front)
    front.set_contact_info.side_effect = BadContactInfoException(
        EMAIL, 'test input', 'test output')
    notifier = Mock(speck=Notifier)
    front_contact_updater = FrontContactUpdater(
        front=front, notifier=notifier)
    reservation = get_test_reservation(
        True, email='invalid_email_here', guesty_id='whatever')

    for i in range(2):
      front_contact_updater.update_for_reservation_or_alert(reservation)

    self.assertEqual(1, len(notifier.notify.call_args_list))
    notify_call = notifier.notify.call_args_list[0]
    call_args, call_kwargs = notify_call[0], notify_call[1]  # noqa:F841
    notify_subject = call_args[1]
    self.assertEqual(
        'Bad email address probably: invalid_email_here', notify_subject)

  def test_update(self):
    check_in = str_to_tz_dt('2018-05-29 16:00')

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
        check_in=check_in,
        check_out=check_in + timedelta(days=1),
        rental=rental,
        guesty_id='helloworld')
    get_test_reservation(
        True,
        guest=guest,
        check_in=check_in + timedelta(days=1),
        check_out=check_in + timedelta(days=2),
        rental=rental,
        guesty_id='hellomars')

    mock_front = Mock(spec=Front)
    mock_clock = Mock(spec=Clock)
    mock_clock.now.return_value = check_in
    updater = FrontContactUpdater(mock_front, clock=mock_clock)

    updater._update_for_guest(guest)
    expected_info_1 = ContactInfo(
        'The Queen of England Buckingham',
        'checkin: 2018-05-29 16:00\ncheckout: 2018-05-30 16:00\ncity: Bismund',
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
        'checkin: 2018-05-29 16:00\ncheckout: 2018-05-30 16:00\ncity: Bismund',
        'https://app.guesty.com/reservations/helloworld/guests',
        '123-456-7890',
        'blargh@gmail.com')
    self.assertEqual(
        mock_front.set_contact_info.call_args_list[1],
        call(expected_info_2))
