from django.utils.dateparse import parse_datetime

from rentals.models import RENT
from rentals.tests import get_test_owner
from reservations.tests import get_test_reservation
from util.tests import TestCase
from util.timezone import str_to_tz_dt

class StatsTests(TestCase):
  def test_get_stats(self):
    queen_of_spain = get_test_owner(True, username='TheQueenofSpain')
    reservation = get_test_reservation(
        True,
        owner=queen_of_spain,
        check_in=str_to_tz_dt('2018-02-01 16:00'),
        check_out=str_to_tz_dt('2018-03-01 11:00'),
        nickname='Lebanon zero',
        city='Lebanon'
    
  stats.get_stats(
      from_date, to_date, interval, city=None, rental_id=None,
      owner_id=None):
