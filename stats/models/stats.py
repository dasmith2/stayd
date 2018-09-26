""" In all things, to_date is exclusive.

This is basically a statistics cache that lets the owner/operator admin and our
own admin read reports fast. It takes a bit to calculate, say, ADR from scratch
for an entire owner over a year! You have to scan all the reservations that
overlap with that year.

This is going to cache all the stats on a month basis and on a daily basis for
everything from owner totals down to individual rentals, and every grouping
inbetween. In order to pull back a year, March through February, say, pull back
the 12 individual months and add them together.

stats.py is all about computing and retrieving the stats.

stale.py is the brains that decides when to ask stats to compute stuff and then
stores it in the database.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.db import models
from django.contrib.auth.models import User

from rentals.models import Rental
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
