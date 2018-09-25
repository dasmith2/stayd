from datetime import datetime


DATE_FORMAT = '%m-%d-%Y'


def date_from_url_str(date_str):
  return datetime.strptime(date_str, DATE_FORMAT).date()


def date_to_url_str(dte):
  return dte.strftime(DATE_FORMAT)


def dates_from_strs(from_date_str, to_date_str):
  from_date = date_from_url_str(from_date_str)
  to_date = date_from_url_str(to_date_str)
  return (from_date, to_date)
