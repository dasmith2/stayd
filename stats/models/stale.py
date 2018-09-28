"""
stale.py is the brains that decides when to recompute stats and then store them
in the database.

Let's try to make this thing perfect. We mark a row as stale once it's stale,
but otherwise we can safely assume the row is up to date. But this is a bit
less complicated than I thought at first. In order to calculate the stats for a
month, you have to calculate all the day stats because reservations can span
months. So since you have to do all the days anyway, we'll only mark the top
level month stale and we'll get the days and weeks along the way when we
resolve the month. We'll kick off background tasks to recalculate everything
that's stale.

Getter is blissfully unaware of what all the exact stats are. """
from datetime import date

from django.db import models
from django.dispatch import receiver

from reservations.models import Reservation
from stats.models.computer import compute_stats
from stats.models.stats import Stats, MONTH, DAY
from util.background import background
from util.rm_old import RmOldManager
from util.signals import post_sync
from util.timezone import add_months


class StaleManager(models.Manager):
  def mark_stale_due_to_reservation(self, reservation):
    to_return = []
    for from_date in self._get_month_from_dates(
        reservation.check_in.date(),
        reservation.check_out.date()):
      for stats in self._get_all_month_stats(reservation.rental, from_date):
        stale = self._mark_stats_stale(
            stats, 'Reservation {}'.format(reservation.pk))
        if stale:
          to_return.append(stale)
    return to_return

  def fix_stale_due_to_reservation(self, reservation):
    for stale in self.mark_stale_due_to_reservation(reservation):
      self.fix(stale)

  def fix(self, stale=None, verbose=False):
    stales = [stale]
    if not stale:
      stales = self.filter(fixing=False)
    for stale in stales:
      stale.fixing = True
      stale.save()
      if verbose:
        print((
            'Fixing from_date {} {} owner {} city {} rental {} reason {} '
            'created_at {}').format(
                stale.stats.from_date, stale.stats.interval,
                stale.stats.owner, stale.stats.city, stale.stats.rental,
                stale.reason, stale.created_at))

      do_fix(stale)

  def mark_all_stats_stale(self, verbose=False):
    total_stales = 0
    for stats in Stats.objects.filter(interval=MONTH):
      if Stale.objects._mark_stats_stale(stats, 'Redoing all stats!'):
        total_stales += 1
    for reservation in Reservation.objects.all():
      total_stales += len(
          Stale.objects.mark_stale_due_to_reservation(reservation))
    if verbose:
      print('{} stale month stats.'.format(total_stales))

  def _get_all_month_stats(self, rental, from_date):
    """ Please let this be the only place we create MONTH stats. Return stats
    down to the rental, up to the owner, and every grouping inbetween. If we
    ever start keeping track of buildings, that'll go here too. """
    if from_date.day != 1:
      raise Exception('Month start dates are always on the first.')
    return [
        # Owner, a.k.a. top level
        Stats.objects.get_or_create(
            from_date=from_date, interval=MONTH, owner=rental.owner,
            city=None, rental=None)[0],
        # City level, a.k.a. a grouping in the middle. In this case you need to
        # specify owner and city.
        Stats.objects.get_or_create(
            from_date=from_date, interval=MONTH, owner=rental.owner,
            city=rental.city, rental=None)[0],
        # Rental, a.k.a. lowest level. In this case owner and city are
        # redundant and should be left None.
        Stats.objects.get_or_create(
            from_date=from_date, interval=MONTH, owner=None, city=None,
            rental=rental)[0]]

  def _get_month_from_dates(self, from_date, to_date):
    on_date = date(from_date.year, from_date.month, 1)
    while on_date < to_date:
      yield on_date
      on_date = add_months(on_date, 1)

  def _mark_stats_stale(self, stats, reason):
    stale, created = self.get_or_create(stats=stats, fixing=False)
    if created:
      stale.reason = reason
      stale.save()
      return stale


@receiver(post_sync, sender=Reservation)
def post_sync(sender, instance, *args, **kwargs):
  if instance.confirmed():
    # Big debate in my head for whether we should fix right away, like,
    # Stale.objects.fix_stale_due_to_reservation(instance) or just mark stale
    # and let an hourly task fix the stales. I think we have to just mark
    # because sometimes guesty likes to inundate us with webhooks for who knows
    # what reason and I don't want them to DOS the worker thread.
    Stale.objects.mark_stale_due_to_reservation(instance)


@background
def do_fix(stale):
  if stale.stats.interval != MONTH:
    raise Exception(stale.stats.interval)
  city = stale.stats.city
  rental_id = None
  if stale.stats.rental:
    rental_id = stale.stats.rental.pk
  owner_id = None
  if stale.stats.owner:
    owner_id = stale.stats.owner.pk

  from_date = stale.stats.from_date
  to_date = add_months(from_date, 1)

  month_point = Stats(from_date=stale.stats.from_date, interval=MONTH)
  for day_point in compute_stats(
      from_date, to_date, DAY, city=city, rental_id=rental_id,
      owner_id=owner_id):
    month_point.add(day_point)
    save_point_to_stats(
        day_point, stale.stats.owner, stale.stats.city, stale.stats.rental)
  save_point_to_stats(
      month_point, stale.stats.owner, stale.stats.city, stale.stats.rental,
      existing_stats=stale.stats)
  OldStale.objects.create(
      stats=stale.stats, reason=stale.reason,
      stale_created_at=stale.created_at)
  stale.delete()


def save_point_to_stats(point, owner, city, rental, existing_stats=None):
  if not existing_stats:
    existing_stats = Stats.objects.get_or_create(
        from_date=point.from_date,
        interval=point.interval,
        owner=owner,
        city=city,
        rental=rental)[0]
  point.owner = owner
  point.city = city
  point.rental = rental
  point.pk = existing_stats.pk
  point.save()
  return point


class Stale(models.Model):
  stats = models.ForeignKey(Stats, on_delete=models.CASCADE, help_text=(
      'Which Stats is stale?'))
  fixing = models.BooleanField(default=False, help_text=(
      'Are we in the middle of fixing this thing?'))
  reason = models.TextField(
      help_text='Just a little explanation of why this is stale.')
  created_at = models.DateTimeField(auto_now_add=True, db_index=True)

  objects = StaleManager()


class OldStale(models.Model):
  """ Since Stale objects are being created and deleted all the time, let's
  keep track of the history of that for a bit. """
  stats = models.ForeignKey(Stats, on_delete=models.CASCADE, help_text=(
      'Which Stats is stale?'))
  reason = models.TextField(
      help_text='Just a little explanation of why this was stale.')
  stale_created_at = models.DateTimeField(help_text=(
      'When was the original Stale, now deleted, created at?'))
  created_at = models.DateTimeField(
      auto_now_add=True, db_index=True, help_text=(
          'When was this record of a Stale created, a.k.a. when the '
          'stale itself was resolved and deleted.'))

  objects = RmOldManager()
