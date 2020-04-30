from collections import namedtuple
from datetime import date, timedelta

from rentals.models import Rental
from stats.models.stats import DAY, WEEK, MONTH, Stats
from util.color import combine_colors
from util.timezone import now, add_months


OccupancyTable = namedtuple('OccupancyTable', 'headers occupancy_rows')
Header = namedtuple('Header', 'week label ideal')
OccupancyRow = namedtuple('OccupancyRow', 'nickname occupancy_cells')
OccupancyCell = namedtuple('OccupancyCell', 'occupancy color')

Ideal = namedtuple('Ideal', 'days_out occupancy')
IDEALS = [
    Ideal(0, 85),
    Ideal(7, 80),
    Ideal(14, 70),
    Ideal(21, 60),
    Ideal(28, 50),
    Ideal(45, 40),
    Ideal(90, 30),
    Ideal(120, 20),
    Ideal(180, 10)]

for i in range(len(IDEALS) - 1):
  if IDEALS[i].occupancy <= IDEALS[i + 1].occupancy:
    raise Exception('The ideal occupancies must strictly increase')

# The secret to a readable chart? You get white when you combine the two
# colors.
OVERBOOKED_COLOR = '1f1'
UNDERBOOKED_COLOR = 'f1f'


def combine_booked_colors(overbooked_weight, underbooked_weight):
  return combine_colors(
      OVERBOOKED_COLOR, overbooked_weight, UNDERBOOKED_COLOR,
      underbooked_weight)


WELLBOOKED_COLOR = combine_booked_colors(1, 1)


def get_color_by_day(day, actual_occupancy, nnow):
  return get_color(_get_ideal_occupancy(day, nnow), actual_occupancy)


def get_color(ideal_occupancy, actual_occupancy):
  underbooked = actual_occupancy < ideal_occupancy
  overbooked = ideal_occupancy < actual_occupancy
  if underbooked:
    return combine_booked_colors(
        1 - (ideal_occupancy - actual_occupancy) / 100, 1)
  elif overbooked:
    return combine_booked_colors(
        1, 1 - (actual_occupancy - ideal_occupancy) / 100)
  return combine_booked_colors(1, 1)


def get_linear_occupancy(interval, nnow):
  """ Here it's one day (or week or month) per column. """
  from_date = nnow.date()
  to_date = from_date + timedelta(days=240)
  if interval == WEEK:
    from_date = previous_sunday(from_date)
    to_date = previous_sunday(to_date)
  if interval == MONTH:
    from_date = from_date.replace(day=1)
    to_date = to_date.replace(day=1)
  rental_lookup = _get_rental_lookup()

  on_rental_occupancy = None
  occupancy_rows = []
  headers = _get_headers(from_date, to_date, interval, nnow)
  at_header = 0

  # Combo units, for instance, don't have an apartment number, so that's why I
  # also order by rental nickname.
  statses = Stats.objects.filter(
      interval=interval, from_date__gte=from_date,
      from_date__lt=to_date, rental__isnull=False).order_by(
          'rental__building', 'rental__apartment', 'rental__nickname',
          'from_date')

  for stats in statses:
    this_nickname = rental_lookup[stats.rental_id].nickname
    if on_rental_occupancy is None or (
        on_rental_occupancy.nickname != this_nickname):
      if on_rental_occupancy:
        _fill_out(headers, at_header, on_rental_occupancy, nnow)
      on_rental_occupancy = OccupancyRow(this_nickname, [])
      occupancy_rows.append(on_rental_occupancy)
      at_header = 0
    while headers[at_header].week < stats.from_date:
      color = get_color_by_day(headers[at_header].week, 0, nnow)
      on_rental_occupancy.occupancy_cells.append(OccupancyCell(0, color))
      at_header += 1
    color = get_color_by_day(stats.from_date, stats.occupancy_rate(), nnow)
    on_rental_occupancy.occupancy_cells.append(
        OccupancyCell(stats.occupancy_rate(), color))
    at_header += 1
  if on_rental_occupancy:
    _fill_out(headers, at_header, on_rental_occupancy, nnow)
  return OccupancyTable(headers, occupancy_rows)


def compress_occupancy(occupancy, nnow):
  """ Take an existing linear occupancy, and compress columns that have the
  same target occupancy together. In other words, now we want 1 column per
  IDEAL. """
  new_headers = []
  new_occupancy_rows = [
      OccupancyRow(ro.nickname, []) for ro in occupancy.occupancy_rows]
  at_index = 0
  old_headers = occupancy.headers
  for ideal in IDEALS:
    # We'll label the new chart according to the first column that matches.
    next_header_week = old_headers[at_index].week
    min_index = at_index
    while ideal.occupancy == old_headers[at_index].ideal:
      at_index += 1
      stop = at_index
      if stop == len(old_headers):
        break
    if min_index == at_index:
      raise Exception('This merge went wrong.')
    label = _get_header_label(next_header_week, nnow)
    new_headers.append(Header(next_header_week, label, ideal.occupancy))
    for i in range(len(occupancy.occupancy_rows)):
      old_rental_occupancy = occupancy.occupancy_rows[i]
      new_rental_occupancy = new_occupancy_rows[i]
      total_occupancy = 0
      for j in range(min_index, stop):
        total_occupancy += old_rental_occupancy.occupancy_cells[j].occupancy
      average_occupancy = int(total_occupancy / (stop - min_index))
      color = get_color(ideal.occupancy, average_occupancy)
      new_rental_occupancy.occupancy_cells.append(
          OccupancyCell(average_occupancy, color))
  return OccupancyTable(new_headers, new_occupancy_rows)


def get_occupancy(nnow=None):
  nnow = nnow or now()
  return compress_occupancy(get_linear_occupancy(DAY, nnow), nnow)


def _fill_out(headers, at_header, on_rental_occupancy, nnow):
  while at_header < len(headers):
    color = get_color_by_day(headers[at_header].week, 0, nnow)
    on_rental_occupancy.occupancy_cells.append(OccupancyCell(0, color))
    at_header += 1


def _get_headers(from_date, to_date, interval, nnow):
  on_date = from_date
  headers = []
  while on_date < to_date:
    label = _get_header_label(on_date, nnow)
    header = Header(on_date, label, _get_ideal_occupancy(on_date, nnow))
    headers.append(header)
    if interval == DAY:
      on_date += timedelta(days=1)
    elif interval == WEEK:
      on_date += timedelta(days=7)
    elif interval == MONTH:
      on_date = add_months(on_date, 1)
  return headers


def _get_header_label(on_date, nnow):
  return '{}, {} days out'.format(
      on_date.strftime('%b %d'), _get_days_out(on_date, nnow))


def _get_days_out(day, nnow):
  return (day - nnow.date()).days


def _get_ideal_occupancy(days_out, nnow):
  if isinstance(days_out, date):
    days_out = _get_days_out(days_out, nnow)
  if days_out <= 0:
    return IDEALS[0].occupancy
  for index, ideal in enumerate(IDEALS):
    if ideal.days_out > days_out:
      # We've gone too far! Have to back up one.
      return IDEALS[index - 1].occupancy
    elif ideal.days_out == days_out:
      return ideal.occupancy
  return ideal.occupancy


def previous_sunday(my_date):
  return my_date - timedelta(days=(8 + my_date.weekday()) % 7)


def _get_rental_lookup():
  lookup = {}
  for rental in Rental.objects.all():
    lookup[rental.pk] = rental
  return lookup
