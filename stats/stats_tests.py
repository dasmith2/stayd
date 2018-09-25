from rentals.models import RENT
from rentals.tests import get_test_owner
from reservations.tests import get_test_reservation
from util.tests import TestCase


class StatsTests(TestCase):
  def test_get_stats(self):
    queen_of_spain = get_test_owner(True, username='TheQueenofSpain')
    
  stats.get_stats(
      from_date, to_date, interval, city=None, rental_id=None,
      owner_id=None):
