""" This thing computes stats from scratch. There are two basic calculations
for a Stats object. First, you compute your fixed costs and resources, a.k.a.,
the stuff that doesn't depend on reservations, a.k.a., rent and nights
available. The second calculation is adding up all the stuff that does depend
on reservations such as revenue, occupied nights, NPS, that kind of thing.
Regarding the second calculation, basically the whole trick is getting all the
reservations that apply, and making a Stats object for each of them. From there
you can multiply each by the appropriate fraction to pro rate each reservation
according to the time span you're interested in. If only 3 out of 6 nights of
that reservation happened in June and you're interested in June, then only half
of the revenue from that reservation applies. Then you just add all of those
fractional Stats together, and you get the total for that time frame.

Stats are computed and stored for atom rentals. A reservation on a combo rental
is split between the atom rentals.
"""
from calendar import monthrange
from datetime import timedelta, date
from decimal import Decimal

from django.contrib.auth.models import User
from django.db.models import Q

from errors.models import log_error
from expenses.models import Expense, DAYS_OF_THE_MONTH
from nps.models.rating import ratings
from rentals.models import Building, Rental, MonthlyExpense, RENT, INSURANCE
from reservations.models import (
    Reservation, KNOWN_LINE_ITEM_NAMES, EXPECT_PAYMENT_DATA_PAST)
from stats.models.stats import DAY, WEEK, MONTH, Stats
from util.channels import (
    AIRBNB, BOOKINGCOM, HOMEAWAY, CANADA_STAYS, NINE_FLATS, DESPEGAR, HOPPIFY,
    MISTER_B_AND_B)
from util.timezone import closest_previous_sunday


def compute_stats(
    from_date, to_date, interval, owner_id=None, city=None, building_id=None,
    rental_id=None):
  """
  Sorry, a bit confusing here. owner_id, city, building_id, rental_id, and
  owner_id are filters and should limit the results. So if you specify an owner
  and a city, then you should only get, say, reservations for that owner in
  that city.

  When we're using owners, buildings, rentals, and reservations,
  we're talking about things that have already been filtered. So if there's a
  list of owners and a list of buildings, pull back all expenses that are for
  either those owners or those buildings. Pop quiz, should you pull back
  reservations for those owners and those buildings? Trick question! Use the
  reservations list which is already appropriately filtered.

  It's ok if compute_stats knows about more filters than getter, city for
  example. That just means that in order to view city stats you have to compute
  them on the fly. They won't be available in the cache. The goal is to be able
  to compute all kinds of wacky stats so folks can get creative with what stats
  they check out, but any stats that show up on a landing page should load ASAP
  and should be cached. """
  owners = User.objects.all()
  buildings = Building.objects.filter(is_active=True)
  rentals = Rental.objects.filter(is_active=True)
  reservations = Reservation.objects.reservations_in_range(from_date, to_date)
  got_ratings = ratings(from_date, to_date)
  if owner_id:
    owners = owners.filter(pk=owner_id)
    buildings = buildings.filter(owner__pk=owner_id)
    rentals = rentals.filter(building__owner__pk=owner_id)
    reservations = reservations.filter(rental__building__owner__pk=owner_id)
    got_ratings = got_ratings.filter(
        reservation__rental__building__owner__pk=owner_id)
  if city:
    owners = []
    buildings = buildings.filter(city=city)
    rentals = rentals.filter(building__city=city)
    reservations = reservations.filter(rental__building__city=city)
    got_ratings = got_ratings.filter(
        reservation__rental__building__city=city)
  if building_id:
    owners = []
    buildings = buildings.filter(pk=building_id)
    rentals = rentals.filter(building__pk=building_id)
    reservations = reservations.filter(rental__building__pk=building_id)
    got_ratings = got_ratings.filter(
        reservation__rental__building__pk=building_id)
  # The building of a combo rental must be identical to the building of the
  # atom rentals. So if we're filtering by building id (or city, or owner)
  # we'll capture reservations for combo rentals and atom rentals. But for
  # rental_id it's a bit different. A combo rental reservation is split between
  # the atom rentals.
  if rental_id:
    owners = []
    buildings = []
    rentals = rentals.filter(pk=rental_id)
    rental = rentals.first()
    if not rental:
      # Stats don't get computed on inactive rentals.
      return []
    if rental.is_combo_rental():
      raise Exception((
          'Stats are computed on atom rentals, not combo rentals '
          'like {}.').format(rental_id))
    reservations = reservations.filter(
        Q(rental__pk=rental_id) | Q(rental__is_combo_of__pk=rental_id))
    got_ratings = got_ratings.filter(reservation__rental__pk=rental_id)

  rentals = rentals.filter(combo_unit_description='')

  lookup = _get_non_reservation_stuff_lookup(
      from_date, to_date, interval, owners, buildings, rentals)

  for reservation in reservations:
    for rental in reservation.rental.get_rentals():
      if rental in rentals:
        # Stats(revenue: $50, cleaning_fees: $10...)
        single_day = single_day_res_stats(reservation, rental)
        on = reservation.check_in.date()
        end = min(reservation.check_out.date(), to_date)
        while on < end:
          key_date = get_key_date(on, interval)
          if key_date in lookup:
            # So, add the daily information from this reservation to the point
            # for this day.
            lookup[key_date].add(single_day)
          on += timedelta(days=1)
  for rating in got_ratings:
    key_date = get_key_date(rating.rating_date(), interval)
    lookup[key_date].total_nps_scores += 1
    if rating.is_promoter():
      lookup[key_date].promoters += 1
    elif rating.is_detractor():
      lookup[key_date].detractors += 1

  return list(sorted(lookup.values(), key=lambda x: x.from_date))


def _get_non_reservation_stuff_lookup(
    from_date, to_date, interval, owners, buildings, rentals):
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
  leases = _get_monthly_expenses(buildings, rentals, RENT)
  insurances = _get_monthly_expenses(buildings, rentals, INSURANCE)
  expenses = _get_day_of_the_month_expenses(
      from_date, to_date, owners, buildings)
  while on < to_date:
    key_date = get_key_date(on, interval)
    if key_date >= from_date:
      if key_date not in lookup:
        lookup[key_date] = Stats(from_date=key_date, interval=interval)
      lookup[key_date].nights_available += _active_rentals(rentals, on)
      lookup[key_date].rent += _get_daily_amount_for_monthly_expenses(
          leases, on)
      lookup[key_date].insurance += _get_daily_amount_for_monthly_expenses(
          insurances, on)
      if expenses:
        key = (key_date.year, key_date.month)
        if key in expenses:
          lookup[key_date].expenses += expenses[key]
    on += timedelta(days=1)
  return lookup


def _active_rentals(rentals, on_date):
  active = 0
  for rental in rentals:
    if rental.reports_start_date <= on_date:
      if (not rental.reports_end_date) or (on_date < rental.reports_end_date):
        active += 1
  return active


def _get_day_of_the_month_expenses(from_date, to_date, owners, buildings):
  """
  {
   (2018, 5): Decimal(100), <- that's the daily value for May
   (2018, 6): Decimal(5)
  }
  """
  expenses = Expense.objects.filter(
      Q(owner__in=owners) | Q(building__in=buildings),
      amortize=DAYS_OF_THE_MONTH)
  if from_date:
    expenses = expenses.filter(month__gte=from_date)
  if to_date:
    expenses = expenses.filter(month__lt=to_date)

  lookup = {}
  for expense in expenses:
    key = (expense.month.year, expense.month.month)
    if key not in lookup:
      lookup[key] = Decimal('0.0')
    lookup[key] += expense.amount.amount
  for key, value in lookup.items():
    lookup[key] = value / monthrange(*key)[1]
  return lookup


def _get_monthly_expenses(buildings, rentals, kind):
  """ Say we got buildings with ids 2 and 5. This will return, like,
  [[building_2_most_recent_monthly_expense, building_2_oldest_monthly_expense],
   [building_5_only_monthly_expense]]
  So it's a list of applicable monthly expense lists. """
  monthly_expenses_lookup = {}
  for monthly_expense in MonthlyExpense.objects.filter(
      Q(rental__building__in=buildings) | Q(rental__in=rentals), kind=kind,
      rental__is_active=True):
    key = monthly_expense.rental.pk
    if key not in monthly_expenses_lookup:
      monthly_expenses_lookup[key] = []
    monthly_expenses_lookup[key].append(monthly_expense)
  for value in monthly_expenses_lookup.values():
    value.sort(key=lambda x: x.start_date)
    value.reverse()
  return monthly_expenses_lookup.values()


def _get_daily_amount_for_monthly_expenses(monthly_expenses, on):
  """ There was lots of hemming and hawing whether rent should be amortized
  over the days of the month or of the year. Advantages to over the year are,
  the daily time series is smoothed out. Advantages to over the month are, the
  reports square a little better with the actual financial flow. It's like,
  rent in February really is more expensive per day, and we would like the
  reports to accurately represent that.

  monthly_expenses should come from _get_monthly_expenses. """
  daily_amount = Decimal(0.0)
  for monthly_expense_list in monthly_expenses:
    for monthly_expense in monthly_expense_list:
      if monthly_expense.start_date <= on:
        daily_amount += monthly_expense.daily_amount(on).amount
        break
  return daily_amount


def get_key_date(on, interval):
  if not isinstance(on, date):
    raise Exception(on)
  if interval == DAY:
    return on
  elif interval == WEEK:
    return closest_previous_sunday(on)
  elif interval == MONTH:
    return on.replace(day=1)
  else:
    raise Exception(interval)


def get_pro_rated_fraction(reservation, from_date, to_date):
  (total_reservation_days, within) = reservation.total_and_within(
      from_date, to_date)
  return 1.0 * within / total_reservation_days


def single_day_res_stats(reservation, rental):
  """ How much of charges, occupied days, etc... for a reservation can be
  attributed to a single day out of that reservation and, now that we have
  combo rentals, for the given rental? """
  res_stats = reservation_res_stats(reservation)

  # You can't do fraction = 1.0 / res_stats.nights_occupied because
  # nights_occupied is 0 for canceled reserations.
  single_day_fraction = 1.0 / reservation.get_night_count()
  res_stats.multiply(single_day_fraction)

  res_stats.multiply(reservation.attributed_to_rental(rental))

  return res_stats


def reservation_res_stats(reservation, nnow=None):
  """ Return the likely total charges, occupied days, and so on for a
  reservation.

  Note that the likely payin for a reservation depends on when you ask! An
  Airbnb reservation with an ideal payin of $100 and an actual payin of $0 has
  a likely payin of $100 on the day of checkin. But an Airbnb reservation with
  an ideal payin of $100 and an actual payin of $0 has a likely payin of $0 a
  week after checkin.

  Make sure this works correctly for these:
  https://app.guesty.com/reservations/5bc918c1b1681c003497155e/financials
  https://app.guesty.com/reservations/5bcbcd471c7c41004a1118db/financials
  """
  res_stats = Stats(
      credit_card_fees=reservation.get_credit_card_fees().amount)
  likely_payin = reservation.get_likely_payin(nnow)
  line_items = reservation.line_items()
  names = KNOWN_LINE_ITEM_NAMES()
  if reservation.canceled():
    # There's a double check for these assumptions in guesty/guesty.py
    # _double_check_canceled_airbnb_reservation
    if reservation.channel == AIRBNB and (
        reservation.check_in > EXPECT_PAYMENT_DATA_PAST):
      for line_item in line_items:
        amount = line_item.value.amount
        if names.is_channel_fee(line_item.name):
          res_stats.channel_fees -= amount
        else:
          res_stats.cancellation_fees += amount
    else:
      res_stats.cancellation_fees += likely_payin.amount
  elif reservation.confirmed():
    if likely_payin:
      _calc_revenue_from_line_items_and_likely_balance_due(
          res_stats, line_items, reservation.get_likely_balance_due(nnow=nnow))
    res_stats.nights_occupied = reservation.get_night_count()
    res_stats.reservation_count = Decimal('1')
  else:
    log_error(
        'unexpected reservation status in stats',
        'reservation {} status {}'.format(reservation.pk, reservation.status))

  # Note that for canceled reservations the rooms_revenue is 0 so the
  # channel_fees are also 0.
  res_stats.channel_fees += _calc_channel_fee(reservation.channel, res_stats)
  return res_stats


def _calc_revenue_from_line_items_and_likely_balance_due(
    res_stats, line_items, likely_balance_due):
  names = KNOWN_LINE_ITEM_NAMES()
  ideal_payin_from_line_items = Decimal('0')
  for line_item in line_items:
    ideal_payin_from_line_items += line_item.value.amount
    # Channel fees are negative and get taken out of the revenue from the
    # room itself. Revenue is every dollar the guest paid and channel fees
    # don't affect that. So in order to calculate revenue, DON'T add the in
    # the channel fee. In other words, revenue is the sum of all non-fee line
    # items. But we don't get all of what the guest paid; we don't get all
    # the revenue. Channel fees get taken out. So to calculate PAYIN you add
    # all line items together including fee line items which are negative.
    # Note that only Airbnb at this time takes out its fee at this level.
    # Booking.com for instance takes it out at the end of the month, so for
    # Booking.com reservations you would expect the payin to equal the
    # revenue.
    amount = line_item.value.amount
    if names.is_channel_fee(line_item.name):
      res_stats.channel_fees -= amount
    elif names.is_cleaning(line_item.name):
      # This line is correct...
      res_stats.cleaning_income += amount
      # But this is just an estimate! We ideally should get a real number
      # we actually paid
      res_stats.cleaning_fees += amount
    elif names.is_tax(line_item.name):
      res_stats.taxes += amount
    elif names.is_rent(line_item.name):
      res_stats.rooms_revenue += amount
    else:
      res_stats.upsell_income += amount
      if not names.is_upsell(line_item.name):
        """
        I used to log these like this, but it's just noise until I figure out
        what to do with these.
        log_error(
            'Unknown line item name', (
                '{} in reservation {}. You might have to update '
                'KNOWN_LINE_ITEM_NAMES in reservations/models.py').format(
                    line_item.name, reservation.pk))
        """
        pass
  # This is a whole thing. If the LIKELY payin, a.k.a. how much we reasonably
  # think we're actually going to get paid, is different from the IDEAL payin,
  # then apply the difference to the rooms_revenue.
  if likely_balance_due:
    res_stats.rooms_revenue -= round(likely_balance_due.amount, 2)
  else:
    # This situation is already alerted about with
    # "Reservation.get_actual_payin is terribly confused" I want this to
    # degrade gracefully so Reservation History will continue to load.
    pass


def _calc_channel_fee(channel, res_stats):
  rooms_revenue_multiplier = Decimal('0')
  cleaning_fee_multiplier = Decimal('0')
  if channel == BOOKINGCOM:
    # Booking.com bills us 15% of the room rate due at the end of the month,
    # so their channel fee isn't in the line items.
    rooms_revenue_multiplier = Decimal('.15')
  if channel == HOMEAWAY:
    rooms_revenue_multiplier = Decimal('.05')
    cleaning_fee_multiplier = Decimal('.05')
  if channel == CANADA_STAYS:
    rooms_revenue_multiplier = Decimal('.08')
  if channel == NINE_FLATS:
    rooms_revenue_multiplier = Decimal('.15')
  if channel == DESPEGAR:
    rooms_revenue_multiplier = Decimal('.15')
  if channel == HOPPIFY:
    rooms_revenue_multiplier = Decimal('.03')
  if channel == MISTER_B_AND_B:
    rooms_revenue_multiplier = Decimal('.055')
  return rooms_revenue_multiplier * res_stats.rooms_revenue + (
      cleaning_fee_multiplier * res_stats.cleaning_income)
