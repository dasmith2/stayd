""" In all things, to_date is exclusive.

This is basically a statistics cache that lets the owner/operator admin and our
own admin read reports fast. It takes a bit to calculate, say, ADR from scratch
for an entire owner over a year! You have to scan all the reservations that
overlap with that year.

This is going to cache all the stats on a month basis and on a daily basis for
everything from owner totals down to individual buildings, and every grouping
inbetween. In order to pull back a year, March through February, say, pull back
the 12 individual months and add them together.

The stats are all DecimalFields, and I'm begining to regret that. I think
FloatField might have been easier to work with.

stats.py simply describes the stats object.

computer.py knows how to compute stats from scratch. This is still being used
by reports/rent_revenue, but ideally that should switch to getter at some
point.

stale.py is the brains that decides when to recompute stats and then store them
in the database.

getter.py knows how to pull back totals and time series from the database.
"""
from decimal import Decimal
import json

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.contrib.auth.models import User
from djmoney.money import Money

from errors.models import log_error
# stats knows about the basic definitions of nps only. Stats is a tool used by
# nps.models.aggregate
from nps.models.rating import nps
from rentals.models import Building, Rental


DAY = 'day'
WEEK = 'week'
MONTH = 'month'
TOTAL = 'total'


INTERVAL_CHOICES = (
    (DAY, DAY),
    (MONTH, MONTH))


class Stats(models.Model):
  # Identifying information. computer.py, getter.py, and stale.py all care
  # about these.
  from_date = models.DateField(db_index=True)
  interval = models.CharField(max_length=10, choices=INTERVAL_CHOICES)
  owner = models.ForeignKey(
      User, null=True, blank=True, on_delete=models.CASCADE)
  building = models.ForeignKey(
      Building, on_delete=models.CASCADE, null=True, blank=True)
  rental = models.ForeignKey(
      Rental, on_delete=models.CASCADE, null=True, blank=True)
  currency = models.CharField(max_length=3, default='USD')

  # Only stats.py and computer.py are concerned with these statistical fields.
  # getter.py and stale.py are blissfully unaware.

  # Income. For the record, "rooms revenue" is the official accounting term.
  rooms_revenue = models.DecimalField(
      decimal_places=4, max_digits=12, default=Decimal(0), help_text=(
          'e.g., $500 because we booked 1 night at $200 and another at $300. '
          'We pretend that a reservation pays the same amount per night.'))
  cleaning_income = models.DecimalField(
      decimal_places=4, max_digits=12, default=Decimal(0), help_text=(
          'This is the cleaning fees we charge guests.'))
  upsell_income = models.DecimalField(
      decimal_places=4, max_digits=12, default=Decimal(0), help_text=(
          'For instance, we charged 5bc823735f041200381b0ae6 $43.50 for an '
          'early checkin.'))
  cancellation_fees = models.DecimalField(
      decimal_places=4, max_digits=12, default=Decimal(0), help_text=(
          'Sometimes we dont give all the money from a cancelled reservation '
          'back, like if they cancel at the last minute'))
  # Expense
  cleaning_fees = models.DecimalField(
      decimal_places=4, max_digits=12, default=Decimal(0), help_text=(
          'This is how much we paid the cleaners.'))
  channel_fees = models.DecimalField(
      decimal_places=4, max_digits=12, default=Decimal(0), help_text=(
          'Booking.com charges 15% at the end of the month. '
          'Put that value here.'))
  taxes = models.DecimalField(
      decimal_places=4, max_digits=12, default=Decimal(0), help_text=(
          'Jersey city taxes hotel stays.'))
  rent = models.DecimalField(
      decimal_places=4, max_digits=12, default=Decimal(0), help_text=(
          'Market rent, what we pay landlords. We pretend that we pay the '
          'same rent every day for the month.'))
  insurance = models.DecimalField(
      decimal_places=4, max_digits=12, default=Decimal(0), help_text=(
          'We pretend we pay the same insurance every day of the month.'))
  expenses = models.DecimalField(
      decimal_places=4, max_digits=12, default=Decimal(0), help_text=(
          'DAYS_OF_THE_MONTH Expenses from expenses.models'))
  nights_occupied_expenses = models.DecimalField(
      decimal_places=4, max_digits=12, default=Decimal(0), help_text=(
          'BOOKED_NIGHTS Expenses from expenses.models'))
  credit_card_fees = models.DecimalField(
      decimal_places=4, max_digits=12, default=Decimal(0), help_text=(
          'Stripe charges us fees when we take Booking.com payments.'))
  # Occupancy
  nights_available = models.PositiveIntegerField(default=0, help_text=(
      'How many nights could we have booked?'))
  nights_occupied = models.PositiveIntegerField(default=0, help_text=(
      'How many nights did we actually book?'))
  reservation_count = models.DecimalField(
      decimal_places=4, max_digits=10, default=Decimal(0), help_text=(
          'How many reservations happened in this time span. If this time '
          'span includes only half of a reservation, then that reservation '
          'contributes 0.5 to this metric.'))
  # Net Promoter Score (NPS)
  promoters = models.PositiveIntegerField(default=0, help_text=(
      'How many reservations whose check-in is in this date range got a '
      'rating of 9 or 10?'))
  detractors = models.PositiveIntegerField(default=0, help_text=(
      'How many reservations whose check-in is in this date range got a '
      'rating of 1-6?'))
  total_nps_scores = models.PositiveIntegerField(default=0, help_text=(
      'How many reservations whose check-in is in this date range got a '
      'rating at all?'))

  def clean(self):
    which_are_set = []
    if self.owner:
      which_are_set.append('owner')
    if self.building:
      which_are_set.append('building')
    if self.rental:
      which_are_set.append('rental')
      if self.rental.is_combo_rental():
        raise ValidationError(
            'Stats go on atom rental, not combo rentals like {}'.format(
                self.rental))
    if len(which_are_set) != 1:
      if not which_are_set:
        which_are_set.append('none of them')
      format_me = (
          'Set exactly one of owner, building, and rental. You\'ve set {}')
      raise ValidationError(format_me.format(', '.join(which_are_set)))

  def nps(self):
    return nps(self.promoters, self.detractors, self.total_nps_scores)

  def average_stay(self):
    if not self.reservation_count:
      if self.nights_occupied:
        raise Exception('How do I have nights occupied but no reservations?')
      return Decimal('0')
    return self.nights_occupied / self.reservation_count

  def total_expenses(self):
    return sum([
        self.rent, self.insurance, self.cleaning_fees, self.channel_fees,
        self.taxes, self.expenses, self.nights_occupied_expenses,
        self.credit_card_fees])

  def pro_rated_expenses(self, pro_rated_fraction):
    return round(Decimal(pro_rated_fraction) * self.total_expenses(), 2)

  def describe_expenses(self, pro_rated_fraction=None):
    details = []
    double_check_amount = Decimal('0')
    possibles = [
        ('Rent', self.rent),
        ('Insurance', self.insurance),
        ('Cleaning fees', self.cleaning_fees),
        ('Channel fees', self.channel_fees),
        ('Taxes', self.taxes),
        ('Bento charges', self.expenses),
        ('Credit card fees', self.credit_card_fees)]
    for name, amount in possibles:
      if amount:
        details.append((name, amount))
        double_check_amount += amount
    if double_check_amount != self.total_expenses():
      if settings.TEST:
        raise Exception(
            'Expenses dont add up: {} vs {}'.format(
                double_check_amount, self.total_expenses()))
      log_error('Expenses dont add up', '{} vs sum({}) in {}'.format(
          self.total_expenses(), details, self.__repr__()))
    details.append(('Total expenses', self.total_expenses()))
    if pro_rated_fraction is not None:
      details.append(
          ('Pro rated expenses', self.pro_rated_expenses(pro_rated_fraction)))
    return details

  def revenue(self):
    return self.rooms_revenue + self.cleaning_income + self.taxes + (
        self.upsell_income + self.cancellation_fees)

  def pro_rated_revenue(self, pro_rated_fraction):
    return round(Decimal(pro_rated_fraction) * self.revenue(), 2)

  def describe_revenue(self, pro_rated_fraction=None):
    details = []
    double_check_amount = Decimal('0')
    possibles = [
        ('Rooms revenue', self.rooms_revenue),
        ('Cleaning income', self.cleaning_income),
        ('Taxes', self.taxes),
        ('Upsell income', self.upsell_income),
        ('Cancellation fees', self.cancellation_fees)]
    for name, amount in possibles:
      if amount:
        details.append((name, amount))
        double_check_amount += amount
    if double_check_amount != self.revenue():
      if settings.TEST:
        raise Exception(
            'Revenue doesnt add up: {} ({}) vs {}'.format(
                double_check_amount, details, self.revenue()))
      log_error('Revenue doesnt add up', '{} vs sum({}) in {}'.format(
          self.revenue(), details, self.__repr__()))
    details.append(('Total revenue', self.revenue()))
    if pro_rated_fraction is not None:
      details.append(
          ('Pro rated revenue', self.pro_rated_revenue(pro_rated_fraction)))
    return details

  def net(self):
    return self.revenue() - self.total_expenses()

  def adr(self):
    """ Average daily rate. It's the average income from occupied nights. """
    if not self.nights_occupied:
      # I used to raise an exception here if there was any income. I was, like,
      # How do I have income without any occupied nights? But cancellation
      # fees.
      return Decimal('0.0')
    return self.revenue() / self.nights_occupied

  def occupancy_rate(self):
    """ Percent of nights with somebody in the apartments compared to total
    nights available in the apartments, expressed as a percentage. """
    if self.nights_available:
      return int(
          Decimal('100.0') * self.nights_occupied / self.nights_available)
    return None

  def rev_par(self):
    """ Average revenue per available room per night. Another way to calculate
    this is by multiplying the adr by the occupancy rate. """
    if self.nights_available:
      return self.revenue() / self.nights_available
    return Decimal('0.0')

  def add(self, stats, include_0_occupancy=True):
    self.rooms_revenue += stats.rooms_revenue
    self.cleaning_income += stats.cleaning_income
    self.upsell_income += stats.upsell_income
    self.cancellation_fees += stats.cancellation_fees
    self.cleaning_fees += stats.cleaning_fees
    self.channel_fees += stats.channel_fees
    self.taxes += stats.taxes
    self.rent += stats.rent
    self.insurance += stats.insurance
    self.expenses += stats.expenses
    self.nights_occupied_expenses += stats.nights_occupied_expenses
    self.credit_card_fees += stats.credit_card_fees

    # We're onboarding units all the time yet we want to be able to brag about
    # the occupancy rates of our existing units. So we need a way to ignore
    # totally empty units. This is used by the Totals report.
    if include_0_occupancy or stats.nights_occupied:
      self.nights_available += stats.nights_available
      self.nights_occupied += stats.nights_occupied

    self.reservation_count += stats.reservation_count
    self.promoters += stats.promoters
    self.detractors += stats.detractors
    self.total_nps_scores += stats.total_nps_scores

  def multiply(self, fraction):
    """ You might use this, for example, to take a stats object that represents
    a 7 day reservation, then multiply it by 3/7ths in order to pro rate that
    reservation's contribution to July or whatever. """
    if fraction.__class__ is float:
      # Otherwise you get unsupported operand type(s) for *=: 'decimal.Decimal'
      # and 'float'. I don't do Decimal(fraction) because that causes weird
      # rounding issues for some reason.
      fraction = Decimal(str(fraction))
    self.rooms_revenue *= fraction
    self.cleaning_income *= fraction
    self.upsell_income *= fraction
    self.cancellation_fees *= fraction
    self.cleaning_fees *= fraction
    self.channel_fees *= fraction
    self.taxes *= fraction
    self.rent *= fraction
    self.insurance *= fraction
    self.expenses *= fraction
    self.nights_occupied_expenses *= fraction
    self.credit_card_fees *= fraction
    self.nights_available *= fraction
    self.nights_occupied = round(self.nights_occupied * fraction)
    self.reservation_count *= fraction
    self.promoters = round(self.promoters * fraction)
    self.detractors = round(self.detractors * fraction)
    self.total_nps_scores = round(self.total_nps_scores * fraction)

  def check_for_money(self):
    """ djmoney.money, holy cow, what a pain. I want to get rid of it. If you
    m = Money(0, 'USD')
    d = Decimal('0')
    d += m
    d is now a Money instance! So Money loves to "upgrade" your classes, and
    then later throw "Cannot add or subtract a Money and non-Money instance."
    or whatever. """
    fields = [
        'rooms_revenue', 'cleaning_income', 'upsell_income',
        'cancellation_fees', 'cleaning_fees', 'channel_fees', 'taxes', 'rent',
        'insurance', 'expenses', 'nights_occupied_expenses',
        'credit_card_fees']
    for field in fields:
      if isinstance(getattr(self, field), Money):
        raise Exception('Alright, who turned {} into money?'.format(field))

  def get_label(self):
    if self.interval == DAY:
      return self.from_date.strftime('%a %b %d')
    elif self.interval == WEEK:
      return self.from_date.strftime('%b %d')
    elif self.interval == MONTH:
      return self.from_date.strftime('%b %Y')

  def to_dict(self):
    dict_v1 = {
        'label': self.get_label(),
        'from_date': self.from_date.strftime('%Y-%m-%d'),
        'interval': self.interval,
        'rooms_revenue': self.rooms_revenue,
        'cleaning_income': self.cleaning_income,
        'upsell_income': self.upsell_income,
        'cancellation_fees': self.cancellation_fees,
        'cleaning_fees': self.cleaning_fees,
        'channel_fees': self.channel_fees,
        'taxes': self.taxes,
        'rent': self.rent,
        'insurance': self.insurance,
        'expenses': self.expenses,
        'nights_occupied_expenses': self.nights_occupied_expenses,
        'credit_card_fees': self.credit_card_fees,
        'nights_available': self.nights_available,
        'nights_occupied': self.nights_occupied,
        'promoters': self.promoters,
        'detractors': self.detractors,
        'total_nps_scores': self.total_nps_scores,
        'nps': self.nps(),
        'total_expenses': self.total_expenses(),
        'revenue': self.revenue(),
        'net': self.net(),
        'adr': self.adr(),
        'occupancy_rate': self.occupancy_rate(),
        'rev_par': self.rev_par(),
        'reservation_count': self.reservation_count,
        'average_stay': self.average_stay()}
    return_me = {}
    for key, value in dict_v1.items():
      # Decimals. Just the worst type. What a pain. Can't json serialize them
      # for one.
      if value.__class__ is Decimal:
        value = float(value)
      return_me[key] = value
    return return_me

  def to_json(self):
    return json.dumps(self.to_dict())

  def save(self, *args, **kwargs):
    # Sorry, hope this isn't too magic. int(True) == 1, and int(False) == 0
    if int(bool(self.owner)) + int(bool(self.building)) + int(
        bool(self.rental)) != 1:
      raise Exception((
          'Specify precisely one of owner {}, building {}, and '
          'rental {}').format(self.owner, self.building, self.rental))
    return super().save(*args, **kwargs)

  class Meta:
    ordering = ['from_date']

  def __repr__(self):
    kind = '???'
    label = '???'
    if self.owner_id:
      kind = 'owner'
      label = self.owner.email
    elif self.building_id:
      kind = 'building'
      label = self.building.nickname
    elif self.rental_id:
      kind = 'rental'
      label = self.rental.nickname
    return '<Stats {}: {} {} {} {}>'.format(
        self.pk, self.from_date, self.interval, kind, label)
