""" The N(et) P(romoter) S(core) is, like, what percentage of our guests are
likely to promote us to their friends a.k.a. promoters, and which are likely to
bad mouth us, a.k.a. detractors. We have the same simple strategy many places
do: ask our guests to rate us.

This file is for basic definitions. It doesn't do anything fancy so it doesn't
know about stats or aggregate. Most other files can safely import things from
this file. """

from django.db import models

from id_verify.models import Submission
from reservations.models import Reservation
from util.fields import OneToOneOrNoneField
from util.table import Table, Cell


def get_or_create_rating(reservation, score):
  if score < 0 or score > 10:
    raise Exception('0 <= score <= 10')
  rating = Rating.objects.filter(reservation=reservation).first()
  if not rating:
    return Rating.objects.create(reservation=reservation, score=score)
  elif rating.score != score:
    rating.score = score
    rating.save()
  return rating


class Rating(models.Model):
  reservation = OneToOneOrNoneField(Reservation, on_delete=models.CASCADE)
  created_at = models.DateTimeField(auto_now_add=True, db_index=True)
  score = models.PositiveIntegerField(help_text='0 <= rating <= 10')
  guest_comment = models.TextField(default='', help_text=(
      'In the case of detractors, we ask them to explain more.'))

  def is_promoter(self):
    return self.score >= 9

  def is_detractor(self):
    return self.score <= 6

  def should_get_comment(self):
    return self.score <= 8

  def neither_promoter_nor_detractor(self):
    return self.score in [7, 8]

  def rating_date(self):
    """ If Bob stays in February and finally gets around to rating us in April,
    the rating should count towards February. """
    return self.reservation.check_in.date()


def nps(promoters, detractors, total_ratings):
  if total_ratings:
    return round(100 * (promoters - detractors) / total_ratings)


def ratings(start_date, end_date):
  return Rating.objects.filter(
      reservation__check_in__date__gte=start_date,
      reservation__check_in__date__lt=end_date).select_related(
          'reservation', 'reservation__guest', 'reservation__rental',
          'reservation__rental__building').order_by('created_at')


def ratings_table(ratings):
  table = Table([
      'Score', 'Guest', 'Email', 'Phone', 'Comment', 'Opt-in email',
      'Check in', 'City', 'Building', 'Rental'])

  reservations = [rating.reservation for rating in ratings]
  submissions = Submission.objects.filter(
      reservation__in=reservations, opt_in_email=True, id_matches_res=True,
      checked_at__isnull=False)
  opt_in_lookup = set()
  for submission in submissions:
    opt_in_lookup.add(submission.reservation_id)

  for rating in ratings:
    reservation = rating.reservation
    guest = reservation.guest
    rental = reservation.rental
    guest_cell = Cell(guest.full_name, url=reservation.admin_url())
    table.create_row([
        rating.score, guest_cell, reservation.get_email(), guest.phone,
        rating.guest_comment, reservation.pk in opt_in_lookup,
        reservation.check_in.date(), rental.building.city.name,
        rental.building.nickname, rental.apartment])
  return table
