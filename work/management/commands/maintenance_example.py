"""
pip install selenium
"""

from util.web_test import WebTest, WebTestCommand
from work.views.web_tests import INDEPENDENT_WORKER_USERNAME


class Command(WebTestCommand):
  help = (
      'Run this from your local machine to create tickets and maintenances on '
      '--server and open up a browser so you can show somebody how '
      '/maintenance/ works.')

  def web_test_classes(self):
    return [MaintenanceWebExample]


class MaintenanceWebExample(WebTest):
  def run(self):
    self.get_2_my_tickets_datas()
    self.open_browser()

  def get_2_my_tickets_datas(self):
    """ This runs on your local machine to fetch a few test maintenance ids
    from the server. """
    return self.server_json(
        'get_2_maintenance_datas_for_web_test')['maintenances']

  def open_browser(self):
    self.server_get('my_tickets', INDEPENDENT_WORKER_USERNAME)
