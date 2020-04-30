from util.web_test import WebTest, WebTestCommand
from util.web_test_users import get_virtual_host


class Command(WebTestCommand):
  help = (
      'Run this from your local machine. '
      'It creates a high risk reservation and then approves it.')

  def web_test_classes(self):
    return [HighRiskWebTest]


class HighRiskWebTest(WebTest):
  def run(self):
    reservation_data = self.server_json(
        'get_reservation_for_high_risk_web_test')
    self.server_get('high_risk_approval', get_virtual_host().username)
    button_finder = '//button[@name="reservation_id" and @value="{}"]'.format(
        reservation_data['pk'])
    self.driver.find_element_by_xpath(button_finder).click()
    assert 0 == len(self.driver.find_elements_by_xpath(button_finder))
