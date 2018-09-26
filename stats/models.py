"""
In all things, to_date is exclusive.

This is basically a big statistics cache that lets the owner/operator admin and
our own admin read reports fast. It takes a bit to calculate, say, ADR from
scratch for an entire owner over a year!  You have to scan all the reservations
that overlap with that year.

This is going to cache all the stats on a month basis and on a daily basis for
everything from owner totals down to individual rentals, and every grouping
inbetween. In order to pull back a year, March through February, say, pull back
the 12 individual months and add them together.

Let's try to make this thing perfect. We mark a row as stale once it's stale,
but otherwise we can safely assume the row is up to date. But this is a bit
less complicated than I thought at first. In order to calculate the stats for a
month, you have to calculate all the day stats because reservations can span
months. So since you have to do all the days anyway, we'll only mark the top
level month stale and we'll get the days and weeks along the way when we
resolve the month. We'll kick off background tasks to recalculate everything
that's stale.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.db import models
from django.contrib.auth.models import User
from django.dispatch import receiver

from rentals.models import Rental
from reports.rent_revenue.time_series import get_points, Point
from reservations.models import Reservation
from util.background import background
from util.rm_old import RmOldManager
from util.signals import post_sync
from util.timezone import add_months


DAY = 'day'
WEEK = 'week'
MONTH = 'month'
TOTAL = 'total'


class StatsManager(models.Manager):
  def get_stats(
      self, from_date, to_date, interval, city=None, rental_id=None,
      owner_id=None):
    rental = None
    owner = None
    # If there's a specific rental, Owner and city are redundant and should be
    # None.
    if rental_id:
      rental = Rental.objects.get(pk=rental_id)
      city = None
    elif owner_id:
      owner = User.objects.get(pk=owner_id)
    elif city:
      raise Exception('If there\'s a city, there must also be an owner.')
    else:
      raise Exception(
          'You should specify a rental id, or an owner id, or a city and an '
          'owner id.')
    if interval in (DAY, MONTH):
      statses = self._get_statses(
          interval, from_date, to_date, city, rental, owner)
      return self._fill_in_gaps(statses, from_date, to_date, interval)
    elif interval == TOTAL:
      return self._get_total(from_date, to_date, city, rental, owner)
    else:
      raise Exception(interval)

  def _get_statses(
      self, search_interval, from_date, to_date, city, rental, owner):
    return self.filter(
        interval=search_interval, start_date__gte=from_date,
        start_date__lt=to_date, city=city, rental=rental, owner=owner)

  def _get_total(self, from_date, to_date, city, rental, owner):
      whole_months_start = from_date
      days_before = Stats()
      if from_date.day != 1:
        whole_months_start = add_months(
            date(from_date.year, from_date.month, 1), 1)
        days_before = self._get_interval_total(
            DAY, from_date, whole_months_start, city, rental, owner)

      whole_months_end = to_date
      days_after = Stats()
      if to_date.day != 1:
        whole_months_end = date(to_date.year, to_date.month, 1)
        days_after = self._get_interval_total(
            DAY, whole_months_end, to_date, city, rental, owner)

      whole_months = self._get_interval_total(
          MONTH, whole_months_start, whole_months_end, city, rental, owner)

      return self._sum_statses(
          [days_before, whole_months, days_after], from_date)

  def _get_interval_total(
      self, interval, from_date, to_date, city, rental, owner):
    if from_date >= to_date:
      return Stats()
    return self._sum_statses(
        self._get_statses(interval, from_date, to_date, city, rental, owner),
        from_date)

  def _sum_statses(self, statses, from_date):
    total = Stats(interval=TOTAL, start_date=from_date)
    for stats in statses:
      total._add(stats)
    return total

  def _fill_in_gaps(self, statses, from_date, to_date, interval):
    on_date = from_date
    to_return = []
    for stats in statses:
      while on_date < stats.start_date:
        to_return.append(Stats(start_date=on_date, interval=interval))
        on_date = self._increment(on_date, interval)
      if on_date > stats.start_date:
        raise Exception(
            'How did on_date {} overtake stats.start_date {}?'.format(
                on_date, stats.start_date))
      to_return.append(stats)
      on_date = self._increment(on_date, interval)
    while on_date < to_date:
      to_return.append(Stats(start_date=on_date, interval=interval))
      on_date = self._increment(on_date, interval)
    return to_return

  def _increment(self, on_date, interval):
    if interval == DAY:
      return on_date + timedelta(days=1)
    elif interval == MONTH:
      return add_months(on_date, 1)
    else:
      raise Exception(interval)

  def _save_point_to_stats(self, point, owner, city, rental, stats=None):
    if not stats:
      stats = Stats.objects.get_or_create(
          start_date=point.from_date,
          interval=point.interval,
          owner=owner,
          city=city,
          rental=rental)[0]
    stats.room_income = point.room_income.amount
    stats.cleaning_income = point.cleaning_income.amount
    stats.cleaning_fees = point.cleaning_fees.amount
    stats.channel_fees = point.channel_fees.amount
    stats.taxes = point.taxes.amount
    stats.rent = point.rent.amount
    stats.nights_available = point.max_occupancy
    stats.nights_occupied = point.occupied_days
    stats.save()
    return stats


INTERVAL_CHOICES = (
    (DAY, DAY),
    (MONTH, MONTH))


class Stats(models.Model):
  start_date = models.DateField()
  interval = models.CharField(max_length=10, choices=INTERVAL_CHOICES)
  owner = models.ForeignKey(
      User, null=True, blank=True, on_delete=models.CASCADE)
  city = models.CharField(max_length=200, null=True, blank=True, db_index=True)
  rental = models.ForeignKey(
      Rental, on_delete=models.CASCADE, null=True, blank=True)
  currency = models.CharField(max_length=3, default='USD')

  # Income
  room_income = models.DecimalField(
      decimal_places=2, max_digits=10, default=Decimal(0), help_text=(
          'e.g., $500 because we booked 1 night at $200 and another at $300. '
          'We pretend that a reservation pays the same amount per night.'))
  cleaning_income = models.DecimalField(
      decimal_places=2, max_digits=10, default=Decimal(0), help_text=(
          'This is the cleaning fees we charge guests.'))
  # Expense
  cleaning_fees = models.DecimalField(
      decimal_places=2, max_digits=10, default=Decimal(0), help_text=(
          'This is how much we paid the cleaners.'))
  channel_fees = models.DecimalField(
      decimal_places=2, max_digits=10, default=Decimal(0), help_text=(
          'Booking.com charges 15% at the end of the month. '
          'Put that value here.'))
  taxes = models.DecimalField(
      decimal_places=2, max_digits=10, default=Decimal(0), help_text=(
          'Jersey city taxes hotel stays.'))
  rent = models.DecimalField(
      decimal_places=2, max_digits=10, default=Decimal(0), help_text=(
          'Market rent, what we pay landlords. We pretend that we pay the '
          'same rent every day for the year, so this is '
          '12 * monthly_rent / 365.'))
  # Occupancy
  nights_available = models.PositiveIntegerField(default=0, help_text=(
      'How many nights could we have booked?'))
  nights_occupied = models.PositiveIntegerField(default=0, help_text=(
      'How many nights did we actually book?'))

  objects = StatsManager()

  def total_expenses(self):
    return self.rent + self.cleaning_fees + self.channel_fees + self.taxes

  def total_income(self):
    return self.room_income + self.cleaning_income

  def net(self):
    return self.total_income() - self.total_expenses()

  def adr(self):
    """ Average daily rate. It's the average income from occupied nights. """
    if not self.nights_occupied:
      if self.total_income():
        raise Exception('How do I have income without any occupied nights?')
      return 0.0
    return self.total_income() / self.nights_occupied

  def occupancy_rate(self):
    """ Percent of nights with somebody in the apartments compared to total
    nights available in the apartments, expressed as a percentage. """
    if self.nights_available:
      return int(100.0 * self.nights_occupied / self.nights_available)
    return 0

  def rev_par(self):
    """ Average revenue per available room per night. Another way to calculate
    this is by multiplying the adr by the occupancy rate. """
    if self.nights_available:
      return self.total_income() / self.nights_available
    return 0.0

  def _add(self, stats):
    self.room_income += stats.room_income
    self.cleaning_income += stats.cleaning_income
    self.cleaning_fees += stats.cleaning_fees
    self.channel_fees += stats.channel_fees
    self.taxes += stats.taxes
    self.rent += stats.rent
    self.nights_available += stats.nights_available
    self.nights_occupied += stats.nights_occupied

  def get_label(self):
    if self.interval == DAY:
      return self.start_date.strftime('%a %b %d')
    elif self.interval == WEEK:
      return self.start_date.strftime('%b %d')
    elif self.interval == MONTH:
      return self.start_date.strftime('%b %Y')

  def to_dict(self):
    return {
        'label': self.get_label(),
        # Refactor to make this consistent. Not sure which name is better.
        'from_date': self.start_date.strftime('%Y-%m-%d'),
        'interval': self.interval,
        'room_income': self.room_income,
        'cleaning_income': self.cleaning_income,
        'cleaning_fees': self.cleaning_fees,
        'channel_fees': self.channel_fees,
        'taxes': self.taxes,
        'rent': self.rent,
        # Refactor to nights_available
        'max_occupancy': self.nights_available,
        # Refactor to nights_occupied
        'occupied_days': self.nights_occupied,
        'total_expenses': self.total_expenses(),
        'total_income': self.total_income(),
        'net': self.net(),
        'adr': self.adr(),
        'occupancy_rate': self.occupancy_rate(),
        'rev_par': self.rev_par()}

  class Meta:
    ordering = ['start_date']


class StaleManager(models.Manager):
  def mark_stale_due_to_reservation(self, reservation):
    to_return = []
    for start_date in self._get_month_start_dates(
        reservation.check_in.date(),
        reservation.check_out.date()):
      for stats in self._get_all_month_stats(reservation.rental, start_date):
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
            'Fixing start_date {} {} owner {} city {} rental {} reason {} '
            'created_at {}').format(
                stale.stats.start_date, stale.stats.interval,
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

  def _get_all_month_stats(self, rental, start_date):
    """ Please let this be the only place we create MONTH stats. Return stats
    down to the rental, up to the owner, and every grouping inbetween. If we
    ever start keeping track of buildings, that'll go here too. """
    if start_date.day != 1:
      raise Exception('Month start dates are always on the first.')
    return [
        # Owner, a.k.a. top level
        Stats.objects.get_or_create(
            start_date=start_date, interval=MONTH, owner=rental.owner,
            city=None, rental=None)[0],
        # City level, a.k.a. a grouping in the middle. In this case you need to
        # specify owner and city.
        Stats.objects.get_or_create(
            start_date=start_date, interval=MONTH, owner=rental.owner,
            city=rental.city, rental=None)[0],
        # Rental, a.k.a. lowest level. In this case owner and city are
        # redundant and should be left None.
        Stats.objects.get_or_create(
            start_date=start_date, interval=MONTH, owner=None, city=None,
            rental=rental)[0]]

  def _get_month_start_dates(self, from_date, to_date):
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

  from_date = stale.stats.start_date
  to_date = add_months(from_date, 1)

  month_point = Point(stale.stats.start_date, MONTH)
  for day_point in get_points(
      from_date, to_date, DAY, city=city, rental_id=rental_id,
      owner_id=owner_id):
    month_point.add(day_point)
    Stats.objects._save_point_to_stats(
        day_point, stale.stats.owner, stale.stats.city, stale.stats.rental)
  Stats.objects._save_point_to_stats(
      month_point, stale.stats.owner, stale.stats.city, stale.stats.rental,
      stats=stale.stats)
  OldStale.objects.create(
      stats=stale.stats, reason=stale.reason,
      stale_created_at=stale.created_at)
  stale.delete()


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
