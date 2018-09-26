from datetime import timedelta
import json

from djmoney.money import Money

from rentals.models import Rental, MonthlyExpense, RENT
from reports.rent_revenue.util import (
    single_day_res_stats, DAY, WEEK, MONTH, ResStats)
from reservations.models import Reservation


class Point(ResStats):
  def __init__(self, from_date, interval, **kwargs):
    self.from_date = from_date
    self.interval = interval
    super().__init__(**kwargs)

  def get_from_date_str(self):
    return self.from_date.strftime('%Y-%m-%d')

  def get_label(self):
    if self.interval == DAY:
      return self.from_date.strftime('%a %b %d')
    elif self.interval == WEEK:
      return self.from_date.strftime('%b %d')
    elif self.interval == MONTH:
      return self.from_date.strftime('%b %Y')

  def to_dict(self):
    return_me = super().to_dict()
    return_me['label'] = self.get_label()
    return return_me

  def to_json(self):
    return json.dumps(self.to_dict())


def get_points(
    from_date, to_date, interval, city=None, rental_id=None, owner_id=None):
  lookup = _get_points_lookup(
      from_date, to_date, interval, city, rental_id, owner_id)
  reservations = Reservation.objects.reservations_in_range(
      from_date, to_date, owner_id)
  if city:
    reservations = reservations.filter(rental__city=city)
  if rental_id:
    reservations = reservations.filter(rental__pk=rental_id)
  for reservation in reservations:
    # Point(total_income: $50, cleaning_fees: $10...)
    single_day = single_day_res_stats(reservation)
    on = reservation.check_in.date()
    end = reservation.check_out.date()
    while on < end:
      key_date = _get_key_date_from_key(on, interval)
      if key_date in lookup:
        # So, add the daily information from this reservation to the point for
        # this day.
        lookup[key_date].add(single_day)
      on += timedelta(days=1)
  return list(sorted(lookup.values(), key=lambda x: x.from_date))


def _get_points_lookup(
    from_date, to_date, interval, city, rental_id, owner_id):
  """
    {
        2018-01-01: Point(nights_available: 10, rent: $200),
        2018-01-02: Point(nights_available: 10, rent: $200)
    }
  """
  lookup = {}
  on = from_date
  rentals = _get_rentals(city, rental_id, owner_id)
  rental_count = len(rentals)
  leases = _get_monthly_expenses(rentals, RENT)
  while on < to_date:
    key_date = _get_key_date_from_key(on, interval)
    if key_date >= from_date:
      if key_date not in lookup:
        lookup[key_date] = Point(from_date=key_date, interval=interval)
      lookup[key_date].nights_available += rental_count
      lookup[key_date].rent += _get_daily_amount(leases, on)
    on += timedelta(days=1)
  return lookup


def _get_rentals(city, rental_id, owner_id):
  rentals = Rental.objects.filter(is_active=True)
  if city:
    rentals = rentals.filter(city=city)
  if rental_id:
    rentals = rentals.filter(pk=rental_id)
  if owner_id:
    rentals = rentals.filter(owner__pk=owner_id)
  return rentals


def _get_monthly_expenses(rentals, kind):
  """ Say we got rentals with ids 2 and 5. This will return, like,
  {2: [most_recent_monthly_expense, oldest_monthly_expense],
   5: [only_monthly_expense]} """
  monthly_expenses_lookup = {}
  for monthly_expense in MonthlyExpense.objects.filter(
      rental__in=rentals, kind=kind):
    key = monthly_expense.rental.pk
    if key not in monthly_expenses_lookup:
      monthly_expenses_lookup[key] = []
    monthly_expenses_lookup[key].append(monthly_expense)
  for value in monthly_expenses_lookup.values():
    value.sort(key=lambda x: x.start_date)
    value.reverse()
  return monthly_expenses_lookup


def _get_daily_amount(monthly_expenses, on):
  """ monthly_expenses should come from _get_monthly_expenses """
  daily_amount = Money(0.0, 'USD')
  for monthly_expense_list in monthly_expenses.values():
    for monthly_expense in monthly_expense_list:
      if monthly_expense.start_date <= on:
        daily_amount += monthly_expense.daily_amount()
        break
  return daily_amount


def _get_key_date_from_key(on, interval):
  if interval == DAY:
    return on
  elif interval == WEEK:
    # Monday == 0, Sunday == 6
    if on.weekday == 6:
      return on
    return on - timedelta(days=on.weekday() + 1)
  elif interval == MONTH:
    return on.replace(day=1)
  else:
    raise Exception(interval)
