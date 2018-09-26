from datetime import date

from djmoney.money import Money

from reservations.models import KNOWN_LINE_ITEM_NAMES
from util.channels import BOOKINGCOM


DAY = 'day'
WEEK = 'week'
MONTH = 'month'
INTERVALS = (DAY, WEEK, MONTH)


class ResStats(object):
  """ Pretty basic object here for keeping track of rent, revenue, fees,
  nights_available available, and occupied days.

  Assumption: Everything is USD all the time! """
  def __init__(
      self, total_income=Money(0, 'USD'), room_income=Money(0, 'USD'),
      cleaning_income=Money(0, 'USD'), cleaning_fees=Money(0, 'USD'),
      channel_fees=Money(0, 'USD'), taxes=Money(0, 'USD'),
      rent=Money(0, 'USD'), nights_available=0, nights_occupied=0):
    self.total_income = total_income
    self.room_income = room_income
    self.cleaning_income = cleaning_income
    self.cleaning_fees = cleaning_fees
    self.channel_fees = channel_fees
    self.taxes = taxes
    self.rent = rent
    # The theoretical maximum number of bookable nights.
    self.nights_available = nights_available
    # How many nights actually got booked.
    self.nights_occupied = nights_occupied

  def add(self, res_stats):
    self.total_income += res_stats.total_income
    self.room_income += res_stats.room_income
    self.cleaning_income += res_stats.cleaning_income
    self.cleaning_fees += res_stats.cleaning_fees
    self.channel_fees += res_stats.channel_fees
    self.taxes += res_stats.taxes
    self.rent += res_stats.rent
    self.nights_available += res_stats.nights_available
    self.nights_occupied += res_stats.nights_occupied

  def multiply(self, fraction):
    self.total_income *= fraction
    self.room_income *= fraction
    self.cleaning_income *= fraction
    self.cleaning_fees *= fraction
    self.channel_fees *= fraction
    self.taxes *= fraction
    self.rent *= fraction
    self.nights_available *= fraction
    self.nights_occupied = round(self.nights_occupied * fraction)

  def total_expenses(self):
    return self.rent + self.cleaning_fees + self.channel_fees + self.taxes

  def net(self):
    return self.total_income - self.total_expenses()

  def adr(self):
    """ Average daily rate. It's the average income from occupied nights. """
    if not self.nights_occupied:
      if self.total_income:
        raise Exception('How do I have charges without any occupied nights?')
      return Money(0.0, 'USD')
    return self.total_income / self.nights_occupied

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
      return self.total_income / self.nights_available
    return Money(0.0, 'USD')

  def to_dict(self):
    dict_stuff = {}
    for key, value in self.__dict__.items():
      dict_stuff[key] = value

    dict_stuff['total_expenses'] = self.total_expenses()
    dict_stuff['net'] = self.net()
    dict_stuff['adr'] = self.adr()
    dict_stuff['occupancy_rate'] = self.occupancy_rate()
    dict_stuff['rev_par'] = self.rev_par()

    return_me = {}
    for key, value in dict_stuff.items():
      dict_val = value
      if value.__class__ is Money:
        dict_val = round(float(value.amount), 2)
      elif value.__class__ is date:
        dict_val = value.strftime('%Y-%m-%d')
      return_me[key] = dict_val
    return return_me


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
  res_stats = ResStats()
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
      if names.is_channel_fee(line_item.name):
        res_stats.channel_fees -= line_item.value
      elif names.is_cleaning(line_item.name):
        # This line is correct...
        res_stats.cleaning_income += line_item.value
        # But this is just an estimate! We ideally should get a real number we
        # actually paid
        res_stats.cleaning_fees += line_item.value
        res_stats.total_income += line_item.value
      elif names.is_tax(line_item.name):
        res_stats.taxes += line_item.value
        res_stats.total_income += line_item.value
      else:
        # This used to be names.is_rent_or_correction(line_item.name),
        # but admins can enter free text for the line item name, so we'll
        # never catch all cases, so I'll just assume everything else
        # is rent or corrections.
        res_stats.room_income += line_item.value
        res_stats.total_income += line_item.value
  if reservation.channel == BOOKINGCOM:
    # Booking.com bills us 15% of the room rate due at the end of the month,
    # so their channel fee isn't in the line items.
    bookingcom_fee = .15 * res_stats.room_income
    res_stats.channel_fees += bookingcom_fee

  res_stats.nights_occupied = (
      reservation.check_out.date() - reservation.check_in.date()).days
  return res_stats
