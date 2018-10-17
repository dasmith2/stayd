""" This thing computes stats from scratch. There are two basic calculations
for a Stats object. First, you compute your fixed costs and resources, a.k.a.,
the stuff that doesn't depend on reservations, a.k.a., rent and nights
available. The second calculation is adding up all the stuff that does depend
on reservations such as revenue, occupied nights, that kind of thing. Regarding
the second calculation, basically the whole trick is getting all the
reservations that apply, and making a Stats object for each of them. From
there you can multiply each by the appropriate fraction to pro rate each
reservation according to the time span you're interested in. If only 3 out of 6
nights of that reservation happened in June and you're interested in June, then
only half of the revenue from that reservation applies. Then you just add all
of those fractional Stats together, and you get the total for that time frame.
"""
from calendar import monthrange
from datetime import timedelta
from decimal import Decimal

from django.db.models import Q

from expenses.models import Expense, DAYS_OF_THE_MONTH
from rentals.models import Building, Rental, MonthlyExpense, RENT
from reservations.models import Reservation, KNOWN_LINE_ITEM_NAMES
from stats.models.stats import DAY, WEEK, MONTH, Stats
from util.channels import BOOKINGCOM


def compute_stats(
    from_date, to_date, interval, city=None, building_id=None, rental_id=None,
    owner_id=None):
  """ It's ok if compute_stats knows about more filters than Stats, city for
  example. That just means that in order to view city stats you have to compute
  them on the fly. They won't be available in the cache. The goal is to be able
  to compute all kinds of wacky stats so folks can get creative with what stats
  they check out, but any stats that show up on a landing page should load ASAP
  and should be cached. """
  # Given our function parameters, what buildings, rentals are we talking about
  # here? a.k.a. non-reservation stuff.
  buildings = Building.objects.filter(is_active=True)
  rentals = Rental.objects.filter(is_active=True)
  if city:
    buildings = buildings.filter(city=city)
    rentals = rentals.filter(building__city=city)
  if building_id:
    buildings = buildings.filter(pk=building_id)
    rentals = rentals.filter(building__pk=building_id)
  if rental_id:
    buildings = []
    rentals = rentals.filter(pk=rental_id)
  if owner_id:
    buildings = buildings.filter(owner__pk=owner_id)
    rentals = rentals.filter(building__owner__pk=owner_id)

  lookup = _get_non_reservation_stuff_lookup(
      from_date, to_date, interval, owner_id, buildings, rentals)

  # Given our function parameters, what reservations are we talking about here?
  reservations = Reservation.objects.reservations_in_range(
      from_date, to_date, owner_id)
  if city:
    reservations = reservations.filter(rental__building__city=city)
  if building_id:
    reservations = reservations.filter(rental__building__pk=building_id)
  if rental_id:
    reservations = reservations.filter(rental__pk=rental_id)
  if owner_id:
    reservations = reservations.filter(rental__building__owner__pk=owner_id)

  for reservation in reservations:
    # Stats(total_income: $50, cleaning_fees: $10...)
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


def _get_non_reservation_stuff_lookup(
    from_date, to_date, interval, owner_id, buildings, rentals):
  """
  OK this basically sets nights_available and rent which are a factor of rental
  units and building leases respectively.
    {
        2018-01-01: Stats(nights_available: 10, rent: $200),
        2018-01-02: Stats(nights_available: 10, rent: $200)
    }
  """
  lookup = {}
  on = from_date
  leases = _get_leases(buildings, rentals, RENT)
  expenses = _get_day_of_the_month_expenses(
      from_date, to_date, owner_id, buildings)
  while on < to_date:
    key_date = _get_key_date_from_key(on, interval)
    if key_date >= from_date:
      if key_date not in lookup:
        lookup[key_date] = Stats(from_date=key_date, interval=interval)
      lookup[key_date].nights_available += _active_rentals(rentals, on)
      lookup[key_date].rent += _get_daily_lease_amount(leases, on)
      if expenses:
        key = (key_date.year, key_date.month)
        if key in expenses:
          lookup[key_date].expenses += expenses[key]
    on += timedelta(days=1)
  return lookup


def _active_rentals(rentals, on_date):
  return sum([1 for rental in rentals if rental.reports_start_date <= on_date])


def _get_day_of_the_month_expenses(from_date, to_date, owner_id, buildings):
  """
  {
   (2018, 5): Decimal(100), <- that's the daily value for May
   (2018, 6): Decimal(5)
  }
  """
  expenses = Expense.objects.filter(amortize=DAYS_OF_THE_MONTH)
  if from_date:
    expenses = expenses.filter(month__gte=from_date)
  if to_date:
    expenses = expenses.filter(month__lt=to_date)
  # Confusing. Ok, if the query is about an owner, then owner_id and buildings
  # will both be set, so we want expenses that are for the owner or for the
  # owner's buildings. If just a building was asked about, then the owner_id
  # won't be set. If an owner has no buildings, then just the owner_id will be
  # something. If no filters were set, then buildings will basically be
  # Buildings.objects.all()
  if owner_id and buildings:
    expenses = expenses.filter(Q(owner=owner_id) | Q(building__in=buildings))
  elif buildings:
    expenses = expenses.filter(building__in=buildings)
  elif owner_id:
    expenses = expenses.filter(owner=owner_id)
  else:
    return None

  lookup = {}
  for expense in expenses:
    key = (expense.month.year, expense.month.month)
    if key not in lookup:
      lookup[key] = Decimal('0.0')
    lookup[key] += expense.amount.amount
  for key, value in lookup.items():
    lookup[key] = value / monthrange(*key)[1]
  return lookup


def _get_leases(buildings, rentals, kind):
  """ Say we got buildings with ids 2 and 5. This will return, like,
  [[building_2_most_recent_monthly_expense, building_2_oldest_monthly_expense],
   [building_5_only_monthly_expense]]
  So it's a list of applicable monthly expense lists. """
  monthly_expenses_lookup = {}
  for monthly_expense in MonthlyExpense.objects.filter(
      Q(rental__building__in=buildings) | Q(rental__in=rentals), kind=kind):
    key = monthly_expense.rental.pk
    if key not in monthly_expenses_lookup:
      monthly_expenses_lookup[key] = []
    monthly_expenses_lookup[key].append(monthly_expense)
  for value in monthly_expenses_lookup.values():
    value.sort(key=lambda x: x.start_date)
    value.reverse()
  return monthly_expenses_lookup.values()


def _get_daily_lease_amount(monthly_expenses, on):
  """ monthly_expenses should come from _get_leases """
  daily_amount = Decimal(0.0)
  for monthly_expense_list in monthly_expenses:
    for monthly_expense in monthly_expense_list:
      if monthly_expense.start_date <= on:
        daily_amount += monthly_expense.daily_amount().amount
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


def pro_rated_res_stats(reservation, from_date, to_date):
  """ How much of charges, occupied days, etc... for a reservation can be
  attributed to happening in the given date range, given the check in
  and check out of the reservation? """
  res_stats = reservation_res_stats(reservation)
  (total_reservation_days, within) = reservation.total_days_and_within_from_to(
      from_date, to_date)
  fraction = 1.0 * within / total_reservation_days
  res_stats.multiply(fraction)
  return res_stats


def single_day_res_stats(reservation):
  """ How much of charges, occupied days, etc... for a reservation can be
  attributed to a single day out of that reservation? Well, occupied days
  should always be 1 in this case. """
  res_stats = reservation_res_stats(reservation)
  fraction = 1.0 / res_stats.nights_occupied
  res_stats.multiply(fraction)
  return res_stats


def reservation_res_stats(reservation):
  """ Return the total charges, occupied days, and so on for a reservation. """
  res_stats = Stats()
  line_items = reservation.line_items()
  if line_items:
    names = KNOWN_LINE_ITEM_NAMES()
    # Typical example: $1262 accommodation fare, $100 cleaning fee,
    # $-40.86 Host channel fee. Then the host payout will be $1321.14.
    # But $100 of that goes straight to cleaners. So revenue is $1221.14.
    for line_item in line_items:
      # Channel fees are negative and get taken out of the revenue from the
      # room itself. In other words, they're don't affect the total charges
      # for the guest. They only affect our bottom line. For booking.com
      # reservations, these channel fees are so high we change the
      # nightly rate to make up for it.
      amount = line_item.value.amount
      if names.is_channel_fee(line_item.name):
        res_stats.channel_fees -= amount
      elif names.is_cleaning(line_item.name):
        # This line is correct...
        res_stats.cleaning_income += amount
        # But this is just an estimate! We ideally should get a real number we
        # actually paid
        res_stats.cleaning_fees += amount
      elif names.is_tax(line_item.name):
        res_stats.taxes += amount
      else:
        # This used to be names.is_rent_or_correction(line_item.name),
        # but admins can enter free text for the line item name, so we'll
        # never catch all cases, so I'll just assume everything else
        # is rent or corrections.
        res_stats.room_income += amount
  if reservation.channel == BOOKINGCOM:
    # Booking.com bills us 15% of the room rate due at the end of the month,
    # so their channel fee isn't in the line items.
    bookingcom_fee = Decimal('.15') * res_stats.room_income
    res_stats.channel_fees += bookingcom_fee

  res_stats.nights_occupied = (
      reservation.check_out.date() - reservation.check_in.date()).days
  res_stats.reservation_count = Decimal('1')
  return res_stats
