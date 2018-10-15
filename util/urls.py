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
  return datetime.strptime(date_str, DATE_FORMAT).date()


def date_to_url_str(dte):
  return dte.strftime(DATE_FORMAT)


def dates_from_strs(from_date_str, to_date_str):
  from_date = date_from_url_str(from_date_str)
  to_date = date_from_url_str(to_date_str)
  return (from_date, to_date)
