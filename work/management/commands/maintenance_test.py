import requests

from util.html_status_codes import is_server_error
from work.management.commands.maintenance_example import (
    Command as MaintenanceExampleCommand, MaintenanceWebExample)
from work.views.web_tests import INDEPENDENT_WORKER_USERNAME


class Command(MaintenanceExampleCommand):
  help = (
      'Run selenium tests on the /maintenance/ page on --server. '
      'For instance, '
      './manage.py maintenance_test --server=https://stage.stayd.com')

  def web_test_classes(self):
    return [MaintenanceWebTest]


class MaintenanceWebTest(MaintenanceWebExample):
  def run(self):
    maintenances_data = self.get_2_my_tickets_datas()
    maintenance1_data = maintenances_data[0]
    maintenance1_id = maintenance1_data['id']
    self.open_browser()

    self.wait_for_class('play')
    maintenance1_div = self.driver.find_element_by_xpath(
        '//div[@data-maintenance-id="{}"]'.format(maintenance1_id))

    # At first you can click play on either maintenance.
    assert 2 == len(self.get_buttons('play'))

    # Click play on the first maintenance
    maintenance1_div.find_element_by_class_name('play').click()
    self.wait_a_sec()  # For display purposes.
    self.wait_for_class('done_not_done_button')  # For deterministic purposes.

    # Now the only things you can do are stop the current maintenance or check
    # off tickets. There are 2 buttons per ticket, hence 4
    # done_not_done_buttons
    assert 0 == len(self.get_buttons('stop'))
    assert 4 == len(self.get_done_not_done_buttons())
    assert 0 == len(self.get_buttons('play'))

    # Complete the tickets
    for index, ticket_id in enumerate(maintenance1_data['ticket_ids']):
      ticket_div = maintenance1_div.find_element_by_xpath(
          '//div[@data-ticket-id="{}"]'.format(ticket_id))
      by_value = 'true' if index % 2 == 0 else 'false'
      ticket_div.find_element_by_xpath(
          './/input[@value="{}"]'.format(by_value)).click()
      self.wait_a_sec()  # For display purposes.

    self.wait_for_class('stop')
    assert 1 == len(self.get_buttons('stop'))

    # Finish the maintenance
    maintenance1_div.find_element_by_class_name('stop').click()
    self.wait_a_sec()
    self.wait_for_class('reopen')

    # You could theoretically do the other maintenance now.
    assert 1 == len(self.get_buttons('play'))

    # Check with the server that the job is indeed finished
    assert self.is_maintenance_complete(maintenance1_id)

    # Create a ticket and start it now
    self.server_get('maintenance_new_ticket', INDEPENDENT_WORKER_USERNAME)
    self.wait_a_sec()
    self.driver.find_element_by_id('id_description').send_keys(
        'Bring out yer dead')
    self.wait_a_sec()
    self.driver.find_element_by_id('do_it_now').click()
    self.wait_a_sec()
    self.wait_for_class('done_not_done_button')

  def is_maintenance_complete(self, pk):
    response = requests.get(
        self.server_reverse('is_maintenance_complete', pk=pk))
    if is_server_error(response):
      raise Exception('Server error', response.status_code, response.content)
    return response.json()['complete']

  def get_buttons(self, class_name):
    return self.driver.find_elements_by_class_name(class_name)

  def get_done_not_done_buttons(self):
    return self.driver.find_elements_by_class_name('done_not_done_button')
