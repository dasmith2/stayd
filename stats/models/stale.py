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

Stale is blissfully unaware of what all the exact stats are. """
from datetime import date, timedelta

from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

from expenses.models import Expense
from nps.models.rating import Rating
from rentals.models import MonthlyExpense, Rental
from reservations.models import Reservation
from stats.models.getter import StatsGetter
from stats.models.computer import compute_stats, get_key_date
from stats.models.stats import Stats, MONTH, WEEK, DAY
from util.background import background
from util.signals import post_sync
from util.timezone import add_months


@receiver(post_save, sender=MonthlyExpense)
def post_save_monthly_expense(sender, instance, *args, **kwargs):
  Stale.objects.mark_stale_due_to_monthly_expense(instance)


@receiver(post_save, sender=Rental)
def post_save_rental(sender, instance, *args, **kwargs):
  """ Stats don't got on combo rentals, they go on atom rentals. So let's say
  somebody just now turns this rental into a combo rental. We must delete all
  stats for this rental, but also mark stale where appropriate for the atom
  rentals so they can be recalculated. """
  if instance.is_combo_rental():
    rentals = instance.get_rentals()
    for stats in Stats.objects.filter(rental=instance):
      if stats.interval == MONTH:
        for rental in rentals:
          from_date = stats.from_date
          to_date = add_months(from_date, 1)
          Stale.objects.mark_from_to_stale(
              rental, from_date, to_date,
              'This rental is now an atom rental for a combo rental.')
      stats.delete()


@receiver(post_sync, sender=Reservation)
def post_sync_reservation(sender, instance, *args, **kwargs):
  if instance.rental.is_active and not instance.get_is_test_reservation():
    # Big debate in my head for whether we should fix right away, like,
    # Stale.objects.fix_stale_due_to_reservation(instance) or just mark stale
    # and let an hourly task fix the stales. I think we have to just mark
    # because sometimes guesty likes to inundate us with webhooks for who knows
    # what reason and I don't want them to DOS the worker thread.
    Stale.objects.mark_stale_due_to_reservation(instance)


@receiver(post_sync, sender=Expense)
def post_sync_expense(sender, instance, *args, **kwargs):
  # Bento periodically syncs its transactions. When it notices a change, it
  # syncs that change to a corresponding Expense, and then triggers a post_sync
  # on that expense. I maintain that layer of indirection so a) other apps will
  # be able to easily plug into creating expenses and therefore updating stats
  # and b) to maintain a separation of stats with bento.
  Stale.objects.mark_stale_due_to_expense(instance)


@receiver(post_save, sender=Rating)
def post_save_rating(sender, instance, *args, **kwargs):
  check_in = instance.reservation.check_in.date()
  Stale.objects.mark_from_to_stale(
      instance.reservation.rental, check_in, check_in + timedelta(days=1),
      'NPS Rating submitted')


class StaleManager(models.Manager):
  def mark_from_to_stale(self, rental, from_date, to_date, reason):
    if rental.is_combo_rental():
      raise Exception(
          'Stats are collected against atom rentals, so it doesnt make sense '
          'to mark stale for combo rental {}.'.format(rental.pk))
    to_return = []
    for from_date in self._get_month_from_dates(from_date, to_date):
      for stats in self._get_all_month_stats(from_date, rental=rental):
        stale = self._mark_stats_stale(stats, reason)
        if stale:
          to_return.append(stale)
    return to_return

  def mark_all_stale(self, verbose=False):
    total_stales = 0
    for stats in Stats.objects.filter(interval=MONTH):
      if Stale.objects._mark_stats_stale(stats, 'Redoing all stats!'):
        total_stales += 1
    if verbose:
      print('{} stale month stats.'.format(total_stales))

  def mark_stale_due_to_expense(self, expense):
    if not expense.building:
      raise Exception('Im expecting expenses with buildings here')
    to_return = []
    for stats in self._get_all_month_stats(
        expense.month, building=expense.building):
      stale = self._mark_stats_stale(stats, 'Expense {}'.format(expense.pk))
      if stale:
        to_return.append(stale)
    return to_return

  def mark_stale_due_to_monthly_expense(self, monthly_expense):
    if not monthly_expense.rental.is_active:
      return
    # I used to have days at 365, but that slowed the tests down quite a bit.
    to_date = monthly_expense.start_date + timedelta(days=62)
    next_expense = MonthlyExpense.objects.filter(
        rental=monthly_expense.rental,
        start_date__gt=monthly_expense.start_date,
        kind=monthly_expense.kind).order_by('start_date').first()
    if next_expense:
      to_date = next_expense.start_date
    return self.mark_from_to_stale(
        monthly_expense.rental, monthly_expense.start_date,
        to_date, 'Monly expense {}'.format(monthly_expense.pk))

  def mark_stale_due_to_reservation(self, reservation):
    if reservation.get_is_test_reservation():
      return []
    to_return = []
    for rental in reservation.rental.get_rentals():
      to_return.extend(self.mark_from_to_stale(
          rental, reservation.check_in.date(),
          reservation.check_out.date(),
          'Reservation {}'.format(reservation.pk)))
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
            'Fixing from_date {} {} owner {} building {} rental {} reason {} '
            'created_at {}').format(
                stale.stats.from_date, stale.stats.interval,
                stale.stats.owner, stale.stats.building, stale.stats.rental,
                stale.reason, stale.created_at))

      do_fix(stale)

  def redo_all_stats(self, verbose=False):
    self.mark_all_stale(verbose=verbose)
    self.fix(verbose=verbose)

  def _get_all_month_stats(self, from_date, rental=None, building=None):
    """ Please let this be the only place we create MONTH stats. If rental,
    return stats for the rental, building, and owner. If building, return stats
    for just the building and owner. """
    if from_date.day != 1:
      raise Exception('Month start dates are always on the first.')
    if int(bool(rental)) + int(bool(building)) != 1:
      raise Exception('Specify exactly one of rental and building')
    to_return = []
    if rental:
      building = rental.building
      # Rental, a.k.a. lowest level.
      to_return.append(Stats.objects.get_or_create(
          from_date=from_date, interval=MONTH,
          rental=rental, building=None, owner=None)[0])
    # Building, a.k.a. middle level.
    to_return.append(Stats.objects.get_or_create(
        from_date=from_date, interval=MONTH,
        rental=None, building=building, owner=None)[0])
    owner = building.owner
    if owner:
      # Owner, a.k.a. top level
      to_return.append(Stats.objects.get_or_create(
          from_date=from_date, interval=MONTH,
          rental=None, building=None, owner=owner)[0])
    return to_return

  def _get_month_from_dates(self, from_date, to_date):
    on_date = date(from_date.year, from_date.month, 1)
    while on_date < to_date:
      yield on_date
      on_date = add_months(on_date, 1)

  def _mark_stats_stale(self, stats, reason):
    if stats.rental and not stats.rental.is_active:
      raise Exception('Dont compute stats on inactive rentals.')
    stale, created = self.get_or_create(stats=stats, fixing=False)
    if created:
      stale.reason = reason
      stale.save()
      return stale


@background
def do_fix(stale):
  if stale.stats.interval == MONTH:
    _do_month_fix(stale)
  else:
    raise Exception(stale.stats.interval)


def _rental_building_owner_id(stale):
  rental_id = None
  if stale.stats.rental:
    rental_id = stale.stats.rental.pk
  building_id = None
  if stale.stats.building:
    building_id = stale.stats.building.pk
  owner_id = None
  if stale.stats.owner:
    owner_id = stale.stats.owner.pk
  return (rental_id, building_id, owner_id)


def _do_month_fix(stale):
  (rental_id, building_id, owner_id) = _rental_building_owner_id(stale)

  from_date = stale.stats.from_date
  to_date = add_months(from_date, 1)

  month_point = Stats(from_date=stale.stats.from_date, interval=MONTH)
  for day_point in compute_stats(
      from_date, to_date, DAY, rental_id=rental_id, building_id=building_id,
      owner_id=owner_id):
    month_point.add(day_point)
    save_point_to_stats(
        day_point, stale.stats.owner, stale.stats.building, stale.stats.rental)
  save_point_to_stats(
      month_point, stale.stats.owner, stale.stats.building, stale.stats.rental,
      existing_stats=stale.stats)

  weeks = set()
  on_date = from_date
  while on_date < to_date:
    week_date = get_key_date(on_date, WEEK)
    if week_date not in weeks:
      _do_week_fix(stale, week_date)
      weeks.add(week_date)
    on_date += timedelta(days=1)

  stale.delete()


def _do_week_fix(month_stale, from_date):
  (rental_id, building_id, owner_id) = _rental_building_owner_id(month_stale)
  if from_date.weekday() != 6:
    raise Exception((
        'from_date doesnt start on Sunday a.k.a. 6, '
        'it starts on {}').format(from_date.weekday()))
  to_date = from_date + timedelta(days=7)
  week_point = Stats(from_date=from_date, interval=WEEK)
  for day_point in StatsGetter().get_stats(
      from_date, to_date, DAY, owner_id=owner_id,
      building_id=building_id, rental_id=rental_id):
    week_point.add(day_point)
  save_point_to_stats(
      week_point, month_stale.stats.owner, month_stale.stats.building,
      month_stale.stats.rental)


def save_point_to_stats(point, owner, building, rental, existing_stats=None):
  if not existing_stats:
    existing_stats = Stats.objects.get_or_create(
        from_date=point.from_date,
        interval=point.interval,
        owner=owner,
        building=building,
        rental=rental)[0]
  point.owner = owner
  point.building = building
  point.rental = rental
  # Hack that overwrites the existing stats with the data from the new one.
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

  def __repr__(self):
    return '<stale for {}>'.format(self.stats.__repr__())
