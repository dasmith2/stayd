from datetime import timedelta
from unittest.mock import Mock

from util.tests import TestCase

from errors.models import Notifier
from guests.tests import get_test_guest
from guest_messages.models.front_contact_updater import FrontContactUpdater
from rentals.tests import get_test_rental
from reservations.tests import get_test_reservation
from util.clock import Clock
from util.timezone import str_to_tz_dt
from front.models import (
    Front, ContactInfoNeedsPushing, EMAIL, PHONE, BadContactInfoException)


class FrontContactUpdaterTests(TestCase):
  def test_alert_bad_number(self):
    front = Mock(speck=Front)
    front.set_contact_info.side_effect = BadContactInfoException(
        PHONE, 'test input', 'test output')
    notifier = Mock(speck=Notifier)
    front_contact_updater = FrontContactUpdater(
        front=front, notifier=notifier)
    reservation = get_test_reservation(
        phone='555-444-3322', guesty_id='whatever')

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
        email='invalid_email_here', guesty_id='whatever')

    for i in range(2):
      front_contact_updater.update_for_reservation_or_alert(reservation)

    self.assertEqual(1, len(notifier.notify.call_args_list))
    notify_call = notifier.notify.call_args_list[0]
    call_args, call_kwargs = notify_call[0], notify_call[1]  # noqa:F841
    notify_subject = call_args[1]
    self.assertEqual(
        'Bad email address probably: invalid_email_here', notify_subject)

  def test_circle_back_around_failed_contact_info_pushes(self):
    mock_front = Mock(spec=Front)
    updater = FrontContactUpdater(mock_front)
    updater._contact_info_for_guest(get_test_reservation().guest).save()

    updater.circle_back_around_failed_contact_info_pushes()
    self.assertEqual(1, len(mock_front.set_contact_info.call_args_list))

  def test_update(self):
    check_in = str_to_tz_dt('2018-05-29 16:00')

    guest = get_test_guest(
        full_name='The Queen of England',
        phone='123-456-7890',
        email='blargh@gmail.com')
    rental = get_test_rental(
        nickname='Buckingham',
        city='Bismund')
    get_test_reservation(
        guest=guest,
        check_in=check_in,
        check_out=check_in + timedelta(days=1),
        rental=rental,
        guesty_id='helloworld')
    get_test_reservation(
        guest=guest,
        check_in=check_in + timedelta(days=1),
        check_out=check_in + timedelta(days=2),
        rental=rental,
        guesty_id='hellomars')

    mock_front = Mock(spec=Front)
    mock_clock = Mock(spec=Clock)
    mock_clock.now.return_value = check_in
    updater = FrontContactUpdater(mock_front, clock=mock_clock)

    updater.update_for_contact_info_or_alert(
        updater._contact_info_for_guest(guest))
    expected_info_1 = ContactInfoNeedsPushing(
        name='The Queen of England Buckingham',
        description=(
            'checkin: 2018-05-29 16:00\ncheckout: 2018-05-30 16:00\n'
            'city: Bismund, ND'),
        link='https://app.guesty.com/reservations/helloworld/guests',
        phone='123-456-7890',
        email='blargh@gmail.com')
    # Sigh, that [0][0][0] is the first call, the first of (args, kwargs) a.k.a
    # args, and then the first arg.
    self.assertTrue(expected_info_1.equals(
        mock_front.set_contact_info.call_args_list[0][0][0]))

    guest.full_name = 'The King of France'
    guest.save()
    updater.update_for_contact_info_or_alert(
        updater._contact_info_for_guest(guest))
    expected_info_2 = ContactInfoNeedsPushing(
        name='The King of France Buckingham',
        description=(
            'checkin: 2018-05-29 16:00\ncheckout: 2018-05-30 16:00\n'
            'city: Bismund, ND'),
        link='https://app.guesty.com/reservations/helloworld/guests',
        phone='123-456-7890',
        email='blargh@gmail.com')
    # So that's the second call, args, first arg.
    self.assertTrue(expected_info_2.equals(
        mock_front.set_contact_info.call_args_list[1][0][0]))
