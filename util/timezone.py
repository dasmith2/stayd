from datetime import datetime, date
import math
import pytz

from django.conf import settings
from django.utils.dateparse import parse_datetime, parse_date
from django.utils.timezone import make_aware, is_aware


def parse_dt(dt_maybe):
  """ This is mainly useful for tests where you wanna do stuff like
  my_res.check_in = parse_dt('2018-05-15 16:00') and have it be made tz aware.
  dt_maybe can be a date, a datetime, or a string representing either
  a date or a datetime. It may be tz aware or not. This function will
  then return a timezone aware datetime. """
  d_or_dt = None
  if dt_maybe.__class__ is str:
    d_or_dt = parse_datetime(dt_maybe) or parse_date(dt_maybe)
  elif dt_maybe.__class__ is datetime or dt_maybe.__class__ is date:
    d_or_dt = dt_maybe
  if not d_or_dt:
    raise Exception('No idea how to get a datetime from {}'.format(dt_maybe))

  if d_or_dt.__class__ is datetime:
    dt_definitely = d_or_dt
  elif d_or_dt.__class__ is date:
    dt_definitely = datetime(d_or_dt.year, d_or_dt.month, d_or_dt.day)
  if is_aware(dt_definitely):
    return dt_definitely
  return make_aware(dt_definitely)


def str_to_tz_dt(dt_str, tz_str=settings.TIME_ZONE):
  """ dt_str is, like, "2012-02-21 10:28:45" while tz_str is, like,
  "Europe/Helsinki". See pytz.all_timezones. This function returns
  something like datetime.datetime(
      2012, 2, 21, 10, 28, 45,
      tzinfo=<DstTzInfo 'Europe/Helsinki' EET+2:00:00 STD>) """
  naive = parse_datetime(dt_str)
  # I THINK is_dst is is daylight savings time and is only used
  # in weird corner cases.
  return pytz.timezone(tz_str).localize(naive, is_dst=None)


def utc_dt_to_tz_dt(tz_dt, tz_str=settings.TIME_ZONE):
  """ Take a timezone aware datetime that's localized to UTC (or whatever,
  but Django stores and loads datetimes in the database in UTC so that's
  pretty much the use case). Let's say tz_dt is noon on Friday UTC. Let's
  say tz_str is US/Eastern. This should return, like, 8am Friday US/Eastern
  because US/Eastern is 4 timezones behind UTC. We need this because if you
  do my_dt.replace(hour=9), it'll do UTC 9am if my_dt is still in UTC, but
  that might be in the middle of the night if what you wanted to do was
  send something at 9am in Hawaii or whatever. """
  return tz_dt.astimezone(pytz.timezone(tz_str))


def default_tzinfo():
  return pytz.timezone(settings.TIME_ZONE)


def midnight_from_date(date_, tzinfo=None):
  tzinfo = tzinfo or default_tzinfo()
  return datetime(
      year=date_.year, month=date_.month, day=date_.day, tzinfo=tzinfo)


def morning_from_date(date_, tzinfo=None):
  tzinfo = tzinfo or default_tzinfo()
  return datetime(
      year=date_.year, month=date_.month, day=date_.day, hour=11,
      tzinfo=tzinfo)


def afternoon_from_date(date_, tzinfo=None):
  tzinfo = tzinfo or default_tzinfo()
  return datetime(
      year=date_.year, month=date_.month, day=date_.day, hour=16,
      tzinfo=tzinfo)


def tz_dt(year, month, day, hour, tzinfo=None):
  tzinfo = tzinfo or default_tzinfo()
  return datetime(
      year=year, month=month, day=day, hour=hour, tzinfo=tzinfo)


def ts_to_utc_dt(time_stamp):
  """ Why utcfromtimestamp doesn't return a dt with the utc timezone is
  beyond me. """
  return datetime.utcfromtimestamp(time_stamp).replace(tzinfo=pytz.utc)


def add_months(daate, months):
  to_year = daate.year
  to_month = daate.month + months
  while to_month > 12:
    to_month -= 12
    to_year += 1
  while to_month < 1:
    to_month += 12
    to_year -= 1
  return date(to_year, to_month, daate.day)


def get_readable_duration(ttimedelta):
  seconds = ttimedelta.seconds
  hours = math.floor(seconds / 3600)
  hours_label = 'hours' if hours != 1 else 'hour'
  minutes = round((seconds % 3600) / 60)
  minutes_label = 'minutes' if minutes != 1 else 'minute'
  return '{} {} {} {}'.format(hours, hours_label, minutes, minutes_label)
