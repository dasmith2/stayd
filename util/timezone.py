import pytz

from django.utils.dateparse import parse_datetime


def str_to_tz_dt(dt_str, tz_str):
  """ dt_str is, like, "2012-02-21 10:28:45" while tz_str is, like,
  "Europe/Helsinki". See pytz.all_timezones. This function returns
  something like datetime.datetime(
      2012, 2, 21, 10, 28, 45,
      tzinfo=<DstTzInfo 'Europe/Helsinki' EET+2:00:00 STD>) """
  naive = parse_datetime(dt_str)
  # I THINK is_dst is is daylight savings time and is only used
  # in weird corner cases.
  return pytz.timezone(tz_str).localize(naive, is_dst=None)


def utc_dt_to_tz_dt(tz_dt, tz_str):
  """ Take a timezone aware datetime that's localized to UTC (or whatever,
  but Django stores and loads datetimes in the database in UTC so that's
  pretty much the use case). Let's say tz_dt is noon on Friday UTC. Let's
  say tz_str is US/Eastern. This should return, like, 7am Friday US/Eastern
  because US/Eastern is 5 timezones behind UTC. We need this because if you
  do my_dt.replace(hour=9), it'll do UTC 9am if my_dt is still in UTC, but
  that might be in the middle of the night if what you wanted to do was
  send something at 9am in Hawaii or whatever. """
  return tz_dt.astimezone(pytz.timezone(tz_str))
