from calendar import monthrange
from datetime import timedelta

from django.shortcuts import render
from django.utils.dateparse import parse_date
from djmoney.money import Money

from errors.models import log_error
from reservations.models import Reservation


def fraction_within_from_to(reservation, from_date, to_date):
  total_revenue = (reservation.check_out - reservation.check_in).days
  within = 0.0
  on = reservation.check_in
  while on < reservation.check_out:
    if from_date <= on and on <= to_date:
      within += 1.0
    on += timedelta(days=1)
  return within / total_revenue


def reservation_revenue(reservation):
  amount = None
  for line_item in reservation.line_items():
    if line_item.name in ('Accommodation fare', 'Host channel fee'):
      if amount is None:
        amount = line_item.value
      else:
        amount += line_item.value
    elif line_item.name in ('Cleaning fee'):
      pass
    else:
      log_error(
          'What do I do with {} line items?'.format(line_item.name),
          'reservation {}'.format(reservation.pk))
  return amount


def pro_rated_month_count(from_date, to_date):
  """ How much, like, month-age is in the date range as expressed as a
  decimal? So 1/15/2018 - 2/28/2018 would return something like 1.5 """
  months = {}
  on = from_date
  while on < to_date:
    key = (on.year, on.month)
    if not key in months:
      months[key] = 1
    else:
      months[key] += 1
    on += timedelta(days=1)
  total_months = 0.0
  for month, days_in_month in months.items():
    total_days_in_month = monthrange(*month)
    total_months += 1.0 * days_in_month / total_days_in_month
  return total_months


class RentRevenue(object):
  def __init__(self, name):
    self.name = name
    self.rent = None
    self.revenue = None

  def add_rent(self, rent):
    if not self.rent:
      self.rent = rent
    else:
      self.rent += rent

  def add_revenue(self, revenue):
    if not self.revenue:
      self.revenue = revenue
    else:
      self.revenue += revenue


def revenue(request, from_date_str, to_date_str):
  from_date = parse_date(from_date_str)
  to_date = parse_date(to_date_str)

  total = RentRevenue('Total')
  by_city = {}
  by_rental = {}

  months = pro_rated_month_count(from_date, to_date)
  for rental in Rental.objects.all():
    pro_rated_rent = rental.market_rent * months
    total.add_rent(pro_rated_rent)
    city = rental.city
    if not city in by_city:
      by_city[city] = RentRevenue(city)
    by_city[city].add_rent(pro_rated_rent)
    nickname = rental.nickname
    if not nickname in by_rental:
      by_rental[nickname] = RentRevenue(nickname)
    by_rental[nickname].add_rent(pro_rated_rent)

  reservations = Reservation.objects.filter(
      check_in__lte=to_date,
      check_out__gte=from_date).select_related('listing', 'listing__rental')
  for reservation in reservations:
    fraction = fraction_within_from_to(reservation, from_date, to_date)
    pro_rated_revenue = fraction * reservation_revenue(reservation)
    total.add_revenue(pro_rated_revenue)
    city = reservation.listing.rental.city
    revenue_by_city[city].add_revenue(pro_rated_revenue)
    nickname = reservation.listing.rental.nickname
    revenue_by_rental[nickname].add_revenue(pro_rated_revenue)

  context = {
      'total': total,
      'by_city': by_city,
      'by_rental': by_rental}
  'reports/rent_revenue.html'
