from datetime import timedelta, date

from work.views.web_tests import CLEAN_CO_OWNER_USERNAME
from util.web_test import WebTest, WebTestCommand
from util.urls import date_to_url_str


class Command(WebTestCommand):
  help = (
      'Run this from your local machine to create a few cleanings for a '
      'cleaning company and open a web page where you can assign cleanings.')

  def web_test_classes(self):
    return [CleanCoExample]


class CleanCoExample(WebTest):
  def run(self):
    self.get_a_bunch_of_cleanings()
    self.open_browser()

  def get_a_bunch_of_cleanings(self):
    """ This runs on your local machine to fetch a few test maintenance ids
    from the server. """
    return self.server_json('get_a_bunch_of_cleanings_for_web_tests')

  def open_browser(self):
    from_str = date_to_url_str(date.today() - timedelta(days=2))
    a_week_str = date_to_url_str(date.today() + timedelta(days=7))
    self.server_get(
        'clean_co_cleanings', CLEAN_CO_OWNER_USERNAME, from_date_str=from_str,
        to_date_str=a_week_str)
