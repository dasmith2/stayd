from datetime import datetime


DATE_FORMAT = '%m-%d-%Y'


def date_from_url_str(date_str):
  return datetime.strptime(date_str, DATE_FORMAT).date()


def date_to_url_str(dte):
  return dte.strftime(DATE_FORMAT)
