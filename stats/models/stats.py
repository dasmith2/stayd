""" In all things, to_date is exclusive.

This is basically a statistics cache that lets the owner/operator admin and our
own admin read reports fast. It takes a bit to calculate, say, ADR from scratch
for an entire owner over a year! You have to scan all the reservations that
overlap with that year.

This is going to cache all the stats on a month basis and on a daily basis for
everything from owner totals down to individual rentals, and every grouping
inbetween. In order to pull back a year, March through February, say, pull back
the 12 individual months and add them together.

stats.py simply describes the stats object.

stale.py is the brains that decides when to recompute stats and then store them
in the database.

getter.py knows how to pull back totals and time series from the database.
"""
from decimal import Decimal

from django.db import models
from django.contrib.auth.models import User

from rentals.models import Rental


DAY = 'day'
WEEK = 'week'
MONTH = 'month'
TOTAL = 'total'


INTERVAL_CHOICES = (
    (DAY, DAY),
    (MONTH, MONTH))


class Stats(models.Model):
  from_date = models.DateField()
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

  def multiply(self, fraction):
    self.room_income *= fraction
    self.cleaning_income *= fraction
    self.cleaning_fees *= fraction
    self.channel_fees *= fraction
    self.taxes *= fraction
    self.rent *= fraction
    self.nights_available *= fraction
    self.nights_occupied = round(self.nights_occupied * fraction)

  def get_label(self):
    if self.interval == DAY:
      return self.from_date.strftime('%a %b %d')
    elif self.interval == WEEK:
      return self.from_date.strftime('%b %d')
    elif self.interval == MONTH:
      return self.from_date.strftime('%b %Y')

  def to_dict(self):
    return {
        'label': self.get_label(),
        # Refactor to make this consistent. Not sure which name is better.
        'from_date': self.from_date.strftime('%Y-%m-%d'),
        'interval': self.interval,
        'room_income': self.room_income,
        'cleaning_income': self.cleaning_income,
        'cleaning_fees': self.cleaning_fees,
        'channel_fees': self.channel_fees,
        'taxes': self.taxes,
        'rent': self.rent,
        # Refactor to nights_available
        'nights_available': self.nights_available,
        # Refactor to nights_occupied
        'nights_occupied': self.nights_occupied,
        'total_expenses': self.total_expenses(),
        'total_income': self.total_income(),
        'net': self.net(),
        'adr': self.adr(),
        'occupancy_rate': self.occupancy_rate(),
        'rev_par': self.rev_par()}

  class Meta:
    ordering = ['from_date']
