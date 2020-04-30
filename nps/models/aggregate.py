""" This file is for the fancy analysis and display of ratings. It knows about
rating.py obviously but also it knows about stats. This file should not get
imported very often. """
from collections import namedtuple
from datetime import date, timedelta

from django.shortcuts import reverse

from guest_messages.models.email import Email
from guesty.custom_field_ids import NPS_RATE_US_EMAIL
from stats.models.stats import Stats, MONTH
from util.color import value_to_color, combine_colors
from util.table import Cell, Table
from util.timezone import (
    now, closest_previous_first_of_the_month, closest_next_first_of_the_month,
    past_x_months, add_months)
from util.urls import date_to_url_str


ROLLING_X_MONTHS = [3, 6, 9, 12]
# Ripped this red and green right out of Excel
GOOD_COLOR = '6c8'
BAD_COLOR = 'f77'
CAUTION_COLOR = combine_colors(GOOD_COLOR, 1, BAD_COLOR, 1)


def get_total_sent_nps_emails():
  return _get_sent_nps_emails().count()


def get_total_opened_nps_emails():
  return _get_sent_nps_emails().filter(opened__isnull=False).count()


def _get_sent_nps_emails():
  return Email.objects.filter(
      template__guesty_custom_field_id=NPS_RATE_US_EMAIL,
      when_did__isnull=False)


def aggregate_ratings_table(nnow=None):
  nnow = nnow or now()
  # to_date is meant to be exclusive.
  to_date = closest_next_first_of_the_month(nnow.date())

  total_with_children = aggregate_data(to_date)
  return _agg_table_from_data(total_with_children, to_date)


class AggregateWithChildren(object):
  def __init__(self, title, query_string):
    self.title = title
    self.query_string = query_string
    # {date(2018, 1, 1): stats_obj, date(2018, 2, 1): stats_obj, ...}
    self.stats_per_month = {}
    # {thing_1: agg_with_children_obj, thing_2: agg_with_children_obj, ...}
    self.children = {}


def aggregate_data(to_date):
  """ Back up a year. Get aaaaall the month stats in that range for rentals.
  Then build a tree of AggregateWithChildren objects. """
  total = AggregateWithChildren('Total', '')

  def add_stats(stats_date, agg_w_children, stats):
    if stats_date not in agg_w_children.stats_per_month:
      agg_w_children.stats_per_month[stats_date] = Stats()
    agg_w_children.stats_per_month[stats_date].add(stats)
    months_before = _months_before(stats.from_date, to_date)
    for rolling in ROLLING_X_MONTHS:
      if rolling >= months_before:
        rolling_key = _rolling_key(to_date, rolling)
        if rolling_key not in agg_w_children.stats_per_month:
          agg_w_children.stats_per_month[rolling_key] = Stats()
        agg_w_children.stats_per_month[rolling_key].add(stats)

  def add_thing(thing, agg_w_children, title, query_string):
    if isinstance(thing, str):
      key = thing
    elif hasattr(thing, 'pk'):
      key = thing.pk
    else:
      raise Exception(thing)
    if key not in agg_w_children.children:
      agg_w_children.children[key] = AggregateWithChildren(title, query_string)
    return agg_w_children.children[key]

  from_date = closest_previous_first_of_the_month(
      to_date - timedelta(days=400))
  all_rental_month_stats = Stats.objects.filter(
      interval=MONTH, from_date__gte=from_date, from_date__lt=to_date,
      rental__isnull=False).select_related(
          'rental', 'rental__building', 'rental__building__city')

  for stats in all_rental_month_stats:
    if stats.total_nps_scores:
      stats_date = stats.from_date
      state = stats.rental.building.city.state
      city = stats.rental.building.city
      building = stats.rental.building
      rental = stats.rental
      if not rental.is_active:
        continue

      add_stats(stats_date, total, stats)

      state_awc = add_thing(state, total, state, 'state={}'.format(state))
      add_stats(stats_date, state_awc, stats)

      city_awc = add_thing(
          city, state_awc, city.name, 'city={}'.format(city.pk))
      add_stats(stats_date, city_awc, stats)

      building_awc = add_thing(
          building, city_awc, building.nickname,
          'building={}'.format(building.pk))
      add_stats(stats_date, building_awc, stats)

      rental_awc = add_thing(
          rental, building_awc, rental.get_apartment(),
          'rental={}'.format(rental.pk))
      add_stats(stats_date, rental_awc, stats)

  return total


def _rolling_key(to_date, months_before):
  return add_months(to_date, -months_before).strftime('Since %m/%d/%y')


def _months_before(from_date, to_date):
  return 12 * (to_date.year - from_date.year) + to_date.month - from_date.month


def nps_to_color(nps):
  return value_to_color(BAD_COLOR, -100, GOOD_COLOR, 100, nps)


def _agg_table_from_data(total_with_children, to_date):
  columns = _columns(to_date)
  table = Table([''] + [column.display for column in columns])

  def _add_row(title, stats_per_month_lookup, query_string):
    row = table.create_row([title])
    for column in columns:
      if column.key in stats_per_month_lookup:
        value = stats_per_month_lookup[column.key].nps()
        base_url = reverse('nps_details', kwargs={
            'from_date_str': date_to_url_str(column.from_date),
            'to_date_str': date_to_url_str(column.to_date)})
        if query_string:
          url = '{}?{}'.format(base_url, query_string)
        else:
          url = base_url
        row.add(Cell(value, url=url, color=nps_to_color(value)))
      else:
        row.add(None)

  def recursive_add(agg_with_children, indent):
    title = agg_with_children.title
    query_string = agg_with_children.query_string
    _add_row(
        Cell(title, is_header=True, classes=['indent_{}'.format(indent)]),
        agg_with_children.stats_per_month, query_string)
    for child in sorted(
        agg_with_children.children.values(), key=lambda x: x.title):
      recursive_add(child, indent + 1)

  recursive_add(total_with_children, 0)

  return table


Column = namedtuple('Column', 'display key from_date to_date')


def _columns(to_date):
  columns = []
  # to_date is exclusive, and past_x_months includes the month of the day you
  # pass it.
  for month in past_x_months(12, add_months(to_date, -1)):
    column_from_date = date(month.year, month.month, 1)
    display = column_from_date.strftime('%B %y')
    key = column_from_date
    column_to_date = add_months(column_from_date, 1)
    columns.append(Column(display, key, column_from_date, column_to_date))
  for months_before in ROLLING_X_MONTHS:
    key = _rolling_key(to_date, months_before)
    display = key
    if to_date.month > months_before:
      column_from_date = date(to_date.year, to_date.month - months_before, 1)
    else:
      column_from_date = date(
          to_date.year - 1, to_date.month + 12 - months_before, 1)
    columns.append(Column(display, key, column_from_date, to_date))
  return columns
