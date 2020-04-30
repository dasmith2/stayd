import json
from unittest.mock import Mock

from django.http import Http404
from django.shortcuts import reverse
from django.test.client import RequestFactory

from guests.tests import get_test_guest
from guesty.custom_field_ids import ID_VERIFIED_FIELD_ID
from guesty.models import RawEvent, GuestyRental, GuestyGuest
from guesty.api import GuestyAPI
from guesty.api_examples import RESERVATION
from guesty.views import turn_on_all_messages
from rentals.tests import get_test_rental
from reservations.tests import get_test_reservation
from util.random_string import random_string
from util.tests import TestCase


def get_test_guesty_guest(**kwargs):
  guest = kwargs.get('guest', None)
  if not guest:
    guest = get_test_guest(**kwargs)
  return GuestyGuest.objects.create(
      guest=guest,
      guesty_id=kwargs.get('guesty_id', random_string()))


def get_test_guesty_rental(**kwargs):
  rental = kwargs.get('rental', None)
  if not rental:
    rental = get_test_rental(**kwargs)
  return GuestyRental.objects.create(
      rental=rental,
      guesty_id=kwargs.get('guesty_id', 'whatever'))


class GuestyRentalTests(TestCase):
  def test_turn_on_all_messages(self):
    guesty_rental = get_test_guesty_rental()
    get_test_reservation(guesty_id='uw', rental=guesty_rental.rental)
    api = Mock(spec=GuestyAPI)
    api.get_one.return_value = {'customFields': []}

    post_request = RequestFactory().post(
        reverse('turn_on_all_messages'),
        {'rental_id': guesty_rental.rental.pk})

    turn_on_all_messages(post_request, api)

    data = {'customFields': []}
    self.assertEqual(1, len(api.put.call_args_list))
    url, data = api.put.call_args_list[0][0]
    self.assertEqual('reservations/uw', url)

    def key(x):
      return x['fieldId']
    got = sorted(data['customFields'], key=key)
    # For grandfathered in reservations, we say the id was verified and
    # therefore turn off any reminders for id verification.
    expected = sorted([
        {'fieldId': ID_VERIFIED_FIELD_ID, 'value': True},
        # Morning of checkout SMS
        {'fieldId': '5afa2c379ebb42009e34f26a', 'value': True},
        # Checkout instructions email (day before checkout)
        {'fieldId': '5afa2c379ebb42009e34f26b', 'value': True},
        # "How\'s everything at the apartment?" SMS (morning after arrival)
        {'fieldId': '5afa2c379ebb42009e34f26c', 'value': True},
        # Day of check-in SMS
        {'fieldId': '5afa2c379ebb42009e34f26d', 'value': True},
        # SMS confirming guest received check-in instructions (2 days
        {'fieldId': '5afa2c379ebb42009e34f26e', 'value': True},
        # Check-in instructions email (2 days before check-in)
        {'fieldId': '5afa2c379ebb42009e34f26f', 'value': True},
        # CANARY_IN_THE_COALMINE_FIELD_ID
        {'fieldId': '5afa2c379ebb42009e34f271', 'value': True},
        # NPS_RATE_US_EMAIL
        {'fieldId': '5d6ed1c2955c1c00240cace7', 'value': True},
        # Reminder to complete ID verification (SMS- 26 hrs after booking)
        {'fieldId': '5afec8950c6ec3001f42e5b2', 'value': False},
        # Request to complete ID verification (SMS- 3 hrs after booking)
        {'fieldId': '5afec8950c6ec3001f42e5b4', 'value': False},
        # 'Request for ID verification (Email- at time of booking)'
        {'fieldId': '5afec8950c6ec3001f42e5b5', 'value': False},
        # 'Message when guest books (on Channel- at time of booking)'
        {'fieldId': '5afec8950c6ec3001f42e5b6', 'value': False},
        # Guest feedback request (SMS 3 days after checkout)
        {'fieldId': '5b299253f2177301cca1269a', 'value': True}], key=key)
    self.assertEqual(expected, got)

  def test_turn_on_all_messages_view(self):
    get_test_rental(nickname='Daves pad')
    url = reverse('turn_on_all_messages')
    self.login(is_superuser=True)
    self.assert_get_contains(url, 'Daves pad')


class WebhookTests(TestCase):
  def test_is_404_reservation(self):
    is_404_event = RawEvent.objects.create(
        json=json.dumps({'reservation': RESERVATION}),
        event_name='reservation.new')
    mock_getter = Mock(spec=GuestyAPI)

    def raise_404(*args):
      raise Http404('Not found!')
    mock_getter.get_one.side_effect = raise_404
    self.assertTrue(is_404_event.check_404_reservation(getter=mock_getter))
    is_404_event.refresh_from_db()
    self.assertTrue(is_404_event.is_404)
    self.assertTrue(bool(is_404_event.handled_at))

  def test_is_not_404_reservation(self):
    not_404 = RawEvent.objects.create(
        json=json.dumps({'reservation': RESERVATION}),
        event_name='reservation.new')
    mock_getter = Mock(spec=GuestyAPI)
    mock_getter.get_one.return_value = RESERVATION
    self.assertFalse(not_404.check_404_reservation(getter=mock_getter))
    not_404.refresh_from_db()
    self.assertFalse(not_404.is_404)
    self.assertFalse(bool(not_404.handled_at))
