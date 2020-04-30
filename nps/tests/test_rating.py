from datetime import date

from id_verify.tests import get_test_submission
from nps.models.rating import (
    Rating, ratings, ratings_table, get_or_create_rating)
from rentals.tests import get_test_building
from reservations.tests import get_test_reservation
from util.table import Cell
from util.tests import TestCase, get_test_user
from util.timezone import str_to_tz_dt


def get_test_rating(**kwargs):
  reservation = kwargs.get('reservation', None)
  if not reservation:
    reservation = get_test_reservation(**kwargs)
  rating = Rating.objects.create(
      reservation=reservation,
      score=kwargs.get('score', 7),
      guest_comment=kwargs.get('guest_comment', ''))
  if 'created_at' in kwargs:
    Rating.objects.filter(pk=rating.pk).update(created_at=kwargs['created_at'])
    rating.refresh_from_db()
  return rating


class RatingsTests(TestCase):
  """ This is a base class. Don't put any actual tests in here. """
  def setUp(self):
    super().setUp()
    self.building_1 = get_test_building(
        nickname='Daves Diner', city='New York')
    reservation_1 = get_test_reservation(
        check_in=str_to_tz_dt('2018-12-25 16:00'),
        check_out=str_to_tz_dt('2018-12-26 11:00'), building=self.building_1,
        apartment='#26', full_name='Billy Barb', guesty_id='aa',
        email='billy@barb.blargh', phone='555-666-7777')
    get_test_submission(
        reservation=reservation_1, opt_in_email=True, id_matches_res=True,
        checked_at=str_to_tz_dt('2018-12-01 12:00'),
        checked_by=get_test_user(), birthday=date(2000, 1, 1))
    self.rating_1 = get_test_rating(
        reservation=reservation_1, score=6,
        guest_comment='Intermittent sprinkles',
        created_at=str_to_tz_dt('2018-12-27 11:00'))
    building_2 = get_test_building(nickname='Fatimas Castle', city='L.A.')
    reservation_2 = get_test_reservation(
        check_in=str_to_tz_dt('2018-12-25 16:00'),
        check_out=str_to_tz_dt('2018-12-26 11:00'), building=building_2,
        apartment='A3', full_name='Susan Splargh', guesty_id='bb',
        email='susan@splargh.net', phone='999-888-7777')
    self.rating_2 = get_test_rating(
        reservation=reservation_2, score=9,
        created_at=str_to_tz_dt('2018-12-28 11:00'))


class RatingsForTableTests(RatingsTests):
  def test_ratings(self):
    self.assertEqual(
        [], list(ratings(date(2018, 11, 1), date(2018, 12, 1))))
    self.assertEqual(
        set([self.rating_1, self.rating_2]),
        set(ratings(date(2018, 12, 1), date(2019, 1, 1))))


class RatingsTableTests(RatingsTests):
  def test_ratings_table(self):
    table = ratings_table([self.rating_1, self.rating_2])
    self.assertEquals([
        'Score', 'Guest', 'Email', 'Phone', 'Comment', 'Opt-in email',
        'Check in', 'City', 'Building', 'Rental'], table.headers)
    billy = Cell(
        'Billy Barb', url='https://app.guesty.com/reservations/aa/guests')
    self.assertEquals([
        6, billy, 'billy@barb.blargh', '555-666-7777',
        'Intermittent sprinkles', True, date(2018, 12, 25), 'New York',
        'Daves Diner', '#26'], table.rows[0].cells)
    susan = Cell(
        'Susan Splargh', url='https://app.guesty.com/reservations/bb/guests')
    self.assertEquals([
        9, susan, 'susan@splargh.net', '999-888-7777', '', False,
        date(2018, 12, 25), 'L.A.', 'Fatimas Castle',
        'A3'], table.rows[1].cells)


class GetOrCreateRatingTests(TestCase):
  def test_get_or_create_rating(self):
    reservation = get_test_reservation()
    get_or_create_rating(reservation, 9)
    reservation.refresh_from_db()
    self.assertEqual(9, reservation.rating.score)
