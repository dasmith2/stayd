import json
from unittest.mock import Mock

from django.http import Http404
from django.test import TestCase

from guesty.models import RawEvent
from guesty.api_getter import GuestyAPIGetter
from guesty.api_examples import RESERVATION


class WebhookTests(TestCase):
  def test_is_404_reservation(self):
    is_404_event = RawEvent.objects.create(
        json=json.dumps({'reservation': RESERVATION}),
        event_name='reservation.new')
    mock_getter = Mock(spec=GuestyAPIGetter)

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
    mock_getter = Mock(spec=GuestyAPIGetter)
    mock_getter.get_one.return_value = RESERVATION
    self.assertFalse(not_404.check_404_reservation(getter=mock_getter))
    not_404.refresh_from_db()
    self.assertFalse(not_404.is_404)
    self.assertFalse(bool(not_404.handled_at))
