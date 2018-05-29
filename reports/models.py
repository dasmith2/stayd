from datetime import timedelta
from errors.models import log_error


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
