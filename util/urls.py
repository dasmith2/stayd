from datetime import datetime
from urllib.parse import urlparse, parse_qsl, urlencode


def url_with(request_get_full_path, key, value):
  url = urlparse(request_get_full_path)
  path = url.path  # /dashboard/
  query_str = url.query  # date=2018-02-15&building_id=1
  # {'date': '2018-02-15', 'building_id': '1'}
  query = dict(parse_qsl(query_str))
  if value is None:
    if key in query:
      del query[key]
  else:
    query[key] = str(value)
  query = urlencode(query)
  if query:
    return '{}?{}'.format(path, query)
  return path


DATE_FORMAT = '%m-%d-%Y'


def date_from_url_str(date_str):
  """ dl hardcoded 09-31-2017 in the url one time. That should just do the
  right thing and return what he meant, the last day in September, 2017-09-30.
  """
  while True:
    try:
      return datetime.strptime(date_str, DATE_FORMAT).date()
    except ValueError as ex:
      if len(ex.args) and ex.args[0] == 'day is out of range for month':
        parts = date_str.split('-')
        date_str = '-'.join((parts[0], str(int(parts[1]) - 1), parts[2]))
      else:
        raise ex


def date_to_url_str(dte):
  """ The datepicker does 05/21/2018, but slashes and urls, so the js turns it
  to dashes first. So these date strings are coming in like 05-21-2018.
  Turn it back to slashes before it goes back out in the context so the
  template can speak the language of the picker. """
  return dte.strftime(DATE_FORMAT)


def dates_from_strs(from_date_str, to_date_str):
  from_date = date_from_url_str(from_date_str)
  to_date = date_from_url_str(to_date_str)
  return (from_date, to_date)


def date_to_date_picker_str(dte):
  return date_to_url_str(dte).replace('-', '/')
