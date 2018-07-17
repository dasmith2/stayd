import json

from util.tests import TestCase

from guesty.api_examples import RESERVATION
from guesty.models import RawEvent
from reports.reservation_history.webhook_describer import WebhookDescriber
from reservations.tests import get_test_reservation
from util.timezone import tz_dt


class TestWebhookDescriber(TestCase):
  def test_get_diffs(self):
    reservation = get_test_reservation(True)
    RawEvent.objects.create(
        json=json.dumps({'reservation': RESERVATION}),
        event_name='reservation.new',
        handled_at=tz_dt(2018, 5, 13, 13),
        reservation=reservation)
    diffs = WebhookDescriber().get_diffs(reservation)
    self.assertEqual(1, len(diffs))
    diff = diffs[0]
    self.assertEqual('reservation.new', diff.event_name)
    self.assertTrue(bool(diff.created_at))
    self.assertEqual(tz_dt(2018, 5, 13, 13), diff.handled_at)
