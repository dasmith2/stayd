from datetime import timedelta
from unittest.mock import Mock, call

from django.test import TestCase
from django.utils.dateparse import parse_datetime

from guests.tests import get_test_guest
from guesty.front_contact_updater import FrontContactUpdater
from guesty.models import GuestyReservation
from rentals.tests import get_test_rental
from reservations.tests import get_test_reservation
from util.clock import Clock
from front.models import Front, ContactInfo


class FrontContactUpdaterTests(TestCase):
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
    res1 = get_test_reservation(
        True,
        guest=guest,
        check_in=now,
        check_out=now + timedelta(days=1),
        rental=rental)
    GuestyReservation.objects.create(reservation=res1, guesty_id='helloworld')
    res2 = get_test_reservation(
        True,
        guest=guest,
        check_in=now + timedelta(days=1),
        check_out=now + timedelta(days=2),
        rental=rental)
    GuestyReservation.objects.create(reservation=res2, guesty_id='hellomars')

    mock_front = Mock(spec=Front)
    mock_clock = Mock(spec=Clock)
    mock_clock.now.return_value = now
    updater = FrontContactUpdater(mock_front, clock=mock_clock)

    updater.update()
    expected_info_1 = ContactInfo(
        'The Queen of England Buckingham',
        'checkin: 2018-05-29 11:00\ncheckout: 2018-05-30 11:00\ncity: Bismund',
        'https://app.guesty.com/reservations/helloworld/guests',
        '123-456-7890',
        'blargh@gmail.com')
    # False here is --verbose
    expected_call = call([expected_info_1], False)
    self.assertEqual(
        mock_front.set_contact_infos.call_args_list, [expected_call])

    guest.full_name = 'The King of France'
    guest.save()
    updater.update_for_guest(guest)
    expected_info_2 = ContactInfo(
        'The King of France Buckingham',
        'checkin: 2018-05-29 11:00\ncheckout: 2018-05-30 11:00\ncity: Bismund',
        'https://app.guesty.com/reservations/helloworld/guests',
        '123-456-7890',
        'blargh@gmail.com')
    self.assertEqual(
        mock_front.set_contact_infos.call_args_list[1],
        call([expected_info_2], False))
