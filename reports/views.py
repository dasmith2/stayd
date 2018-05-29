from calendar import monthrange

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils.dateparse import parse_date
from djmoney.money import Money

from reservations.models import Reservation


class RentRevenue(object):
  def __init__(self, name, sort_value=''):
    self.name = name
    self.sort_value = sort_value or name
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


def revenue_context(from_date_str, to_date_str):
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
      by_rental[nickname] = RentRevenue(nickname, city + nickname)
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

  return {
      'total': total,
      'cities': sorted(by_city.values(), key=lambda rr: rr.sort_value),
      'rentals': sorted(by_rental.values(), key=lambda rr: rr.sort_value)}


@login_required
def rent_revenue(request, from_date_str='', to_date_str=''):
  context = {
      'from_date_str': from_date_str,
      'to_date_str': to_date_str}
  if from_date_str and to_date_str:
    context.update(revenue_context(from_date_str, to_date_str))

  return render(request, 'reports/rent_revenue.html', context=context)
