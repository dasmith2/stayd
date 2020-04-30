from datetime import datetime
from urllib.parse import urlparse, parse_qsl, urlencode

from django.conf import settings
from django.shortcuts import reverse
from util.timezone import now


def data_to_query_string(data):
  if not data:
    return ''
  return '?{}'.format(
      '='.join(['{}={}'.format(*item) for item in data.items()]))


def full_reverse(view_name, args=None, kwargs=None):
  # Do the full url instead of just the path.
  args = args or []
  kwargs = kwargs or {}
  return full_url(reverse(view_name, args=args, kwargs=kwargs))


def full_url(url):
  return '{}{}'.format(settings.THIS_SERVERS_BASE_URL, url)


def keys_url(url):
  return '{}{}'.format(settings.KEYS_SERVER, url)


def keys_reverse(view_name, args=None, kwargs=None, **kwargss):
  args = args or []
  kwargs = kwargs or kwargss or {}
  return keys_url(reverse(view_name, args=args, kwargs=kwargs))


def admin_edit_url(my_object):
  view_name = 'admin:{}_{}_change'.format(
      my_object._meta.app_label, my_object._meta.model_name)
  return reverse(view_name, args=[my_object.pk])


def url_with(request_get_full_path, key, value):
  # Add the given key value pair to the query string. Why is this so hard haha
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


def nnow_from_query(request_get):
  # This is useful for, like, injecting nnow into a web test.
  nnow = now()
  if 'nnow' in request_get:
    nnow_date = date_from_url_str(request_get['nnow'])
    nnow = nnow.replace(
        year=nnow_date.year, month=nnow_date.month, day=nnow_date.day)
  return nnow


def nnow_query(nnow):
  """ This is the inverse of nnow_from_query. It'll return something like
  "?nnow=2018-12-25" """
  if isinstance(nnow, datetime):
    nnow = nnow.date()
  return "?nnow={}".format(date_to_url_str(nnow))


def date_to_url_str(dte):
  """ The datepicker does 05/21/2018, but slashes and urls, so the js turns it
  to dashes first. So these date strings are coming in like 05-21-2018.
  Turn it back to slashes before it goes back out in the context so the
  template can speak the language of the picker. """
  return dte.strftime(DATE_FORMAT)


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


def dates_from_strs(from_date_str, to_date_str):
  from_date, from_error = _date_and_error_from_str(from_date_str)
  to_date, to_error = _date_and_error_from_str(to_date_str)
  error = from_error or to_error
  if not error and from_date > to_date:
    error = 'Your "From" and "To" dates are out of order'
  return (from_date, to_date, error)


def _date_and_error_from_str(date_str):
  my_date = None
  error = None
  try:
    my_date = date_from_url_str(date_str)
  except ValueError as ex:
    if ex.args[0].find('does not match format') >= 0:
      error = (
          'Hey hacker :) I see you\'re manually modifing the date string! '
          'I like that. Just FYI, the format in the query string is '
          'mm-dd-yyyy, and the format in the text box is mm/dd/yyyy. I\'m '
          'seeing {} which doesn\'t quite work.').format(date_str)
  return my_date, error


def date_to_date_picker_str(dte):
  if dte:
    return date_to_url_str(dte).replace('-', '/')
  return ''
