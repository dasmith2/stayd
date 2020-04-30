from collections import namedtuple
from datetime import datetime, date, timedelta, time
import math
import pytz
import re

from django.conf import settings
from django.utils.dateparse import parse_datetime, parse_date
from django.utils.timezone import make_aware, is_aware, now as django_now


def tz_dt_to_str(tz_dt, tz_str=settings.TIME_ZONE):
  """ Jan. 10, 2019, 8:18 a.m.
  I just reverse engineered Django's formula for turning datetimes into
  readable strings. """
  if tz_str:
    tz_dt = tz_dt_to_tz_dt(tz_dt, tz_str)
  return dt_to_str(tz_dt)


def dt_to_str(tz_dt):
  return ''.join([dt_to_date_str(tz_dt), ', ', dt_to_time_str(tz_dt)])


def dt_to_date_str(tz_dt):
  return tz_dt.strftime('%b. %d, %Y')


def dt_to_time_str(tz_dt):
  join_me = []
  minute_str = ''
  if tz_dt.minute > 0:
    if tz_dt.minute >= 10:
      minute_str = ':{}'.format(tz_dt.minute)
    else:
      minute_str = ':0{}'.format(tz_dt.minute)
  if tz_dt.hour < 12:
    join_me.extend([str(tz_dt.hour), minute_str, ' a.m.'])
  elif tz_dt.hour == 12:
    if tz_dt.minute == 0:
      join_me.append('noon')
    else:
      join_me.extend([str(tz_dt.hour), minute_str, ' p.m.'])
  else:
    join_me.extend([str(tz_dt.hour - 12), minute_str, ' p.m.'])
  return ''.join(join_me)


def tz_dt_to_abbr_str(tz_dt, tz_str=settings.TIME_ZONE):
  return tz_dt_to_tz_dt(tz_dt, tz_str).strftime('%Y-%m-%d %H:%M EST')


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


def str_to_naive_dt(dt_str):
  parsed_as_dt = parse_datetime(dt_str)
  if parsed_as_dt:
    return parsed_as_dt
  parsed_as_d = parse_date(dt_str)
  if parsed_as_d:
    return datetime(parsed_as_d.year, parsed_as_d.month, parsed_as_d.day)
  raise Exception('Unable to parse date string {}'.format(dt_str))


def str_to_tz_dt(dt_str, tz_str=settings.TIME_ZONE):
  """ dt_str is, like, "2012-02-21 10:28:45" while tz_str is, like,
  "Europe/Helsinki". See pytz.all_timezones. This function returns
  something like datetime.datetime(
      2012, 2, 21, 10, 28, 45,
      tzinfo=<DstTzInfo 'Europe/Helsinki' EET+2:00:00 STD>)
  dt_str can also be, like, "2012-02-21" which will just do midnight. """
  return naive_dt_to_tz_dt(str_to_naive_dt(dt_str), tz_str)


def naive_dt_to_tz_dt(naive, tz_str=settings.TIME_ZONE):
  # I THINK is_dst is is daylight savings time and is only used in weird corner
  # cases.
  return pytz.timezone(tz_str).localize(naive, is_dst=None)


def tz_dt_to_tz_dt(tz_dt, tz_str=settings.TIME_ZONE):
  """ Take a timezone aware datetime that's localized to UTC (or whatever,
  but Django stores and loads datetimes in the database in UTC so that's
  pretty much the use case). Let's say tz_dt is noon on Friday UTC. Let's
  say tz_str is US/Eastern. This should return, like, 8am Friday US/Eastern
  because US/Eastern is 4 timezones behind UTC. We need this because if you
  do my_dt.replace(hour=9), it'll do UTC 9am if my_dt is still in UTC, but
  that might be in the middle of the night if what you wanted to do was
  send something at 9am in Hawaii or whatever. """
  return tz_dt.astimezone(pytz.timezone(tz_str))


def now():
  # django_now is in UTC, so things like now().date() can return tomorrow if
  # you call it past 7pm.
  return tz_dt_to_tz_dt(django_now())


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


def time_of_day_from_date(date_, hour, tzinfo=None):
  tzinfo = tzinfo or default_tzinfo()
  return datetime(
      year=date_.year, month=date_.month, day=date_.day, hour=hour,
      tzinfo=tzinfo)


def closest_previous_sunday(date_):
  # Monday == 0, Sunday == 6
  if date_.weekday() == 6:
    return date_
  return date_ - timedelta(days=date_.weekday() + 1)


def closest_previous_first_of_the_month(date_):
  return date_.replace(day=1)


def closest_next_first_of_the_month(date_):
  if date_.day == 1:
    return date_
  if date_.month == 12:
    return date(date_.year + 1, 1, 1)
  return date(date_.year, date_.month + 1, 1)


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
  parts = []
  days = ttimedelta.days
  if days > 0:
    parts.append(str(days))
    if days == 1:
      parts.append('day')
    else:
      parts.append('days')
  seconds = ttimedelta.seconds
  if seconds == 0:
    return '0 seconds'
  hours = math.floor(seconds / 3600)
  minutes = round((seconds % 3600) / 60)
  if hours > 0:
    parts.append(str(hours))
    parts.append('hours' if hours != 1 else 'hour')
  if minutes > 0:
    parts.append(str(minutes))
    parts.append('minutes' if minutes != 1 else 'minute')
  return ' '.join(parts)


def describe_timedelta(delta):
  hours, remainder = divmod(delta.seconds, 3600)
  minutes, seconds = divmod(remainder, 60)
  return '{:02}:{:02}'.format(int(hours), int(minutes))


PastMonth = namedtuple('PastMonth', 'year month months_ago')


def past_x_months(x, nnow=None):
  """ Including the 1st of nnow's month """
  if nnow is None:
    nnow_date = date.today()
  elif isinstance(nnow, date):
    nnow_date = nnow
  elif isinstance(nnow, datetime):
    nnow_date = nnow.date()
  else:
    raise Exception(nnow)
  this_month = nnow_date.month
  this_year = nnow_date.year
  for i in range(12):
    next_month = (this_month - 1 - i) % 12 + 1
    next_year = this_year
    if i >= this_month:
      next_year -= 1
    yield PastMonth(next_year, next_month, i)


def years_old(birthdate, nnow=None):
  nnow = nnow or now()
  if not birthdate:
    return None
  today = nnow.date()
  year_delta = today.year - birthdate.year
  if today.month < birthdate.month or (
      today.month == birthdate.month and today.day < birthdate.day):
    return year_delta - 1
  return year_delta


def time_str_to_time(time_str):
  """ time_str can be either, like, '17:00' or '05:00 PM'

  On 4/3/19 our channel manager switched formats from a 24 to a 12 hour
  clock. Then I complained to them. Then I made an alert just in case the old
  format still got used, which it did! So apparently BOTH formats are in play
  now, which is insane. """
  if time_str:
    if re.compile(r'^\d+:\d+$').match(time_str):  # '17:00'
      parts = list(int(p) for p in time_str.split(':'))  # (17, 0)
      return time(*parts)
    found = re.compile(r'(\d+):(\d+) (AM|PM)').match(time_str)  # '05:00 PM'
    if found:
      (hour, minute, am_pm) = found.groups()
      hour = int(hour)
      minute = int(minute)
      # Wikipedia says 11:59 PM means 1 minute before midnight but 12:00 PM
      # means noon and 12:00 AM means midnight.
      if hour == 12:
        if am_pm == 'AM':
          hour -= 12
      elif am_pm == 'PM':
        hour += 12
      return time(hour, minute)
