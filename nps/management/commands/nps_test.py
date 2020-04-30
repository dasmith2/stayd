from nps.management.commands.nps_example import NPSExample
from util.web_test_users import SUPERUSER_USERNAME
from util.web_test import WebTestCommand


class Command(WebTestCommand):
  help = (
      'Run this from your local machine to test collecting NPS ratings and '
      'analyzing the data')

  def web_test_classes(self):
    return [NPSTest]


class NPSTest(NPSExample):
  def run(self):
    self.open_rate_us(5)
    self.wait_for_text("//*[@id='you_rated_us']", '5')
    self.wait_a_sec()
    self.driver.find_element_by_tag_name('textarea').send_keys(
        'I got WAY too much pointless government mail')

    self.driver.find_element_by_tag_name('button').click()
    self.wait_a_sec()

    self.server_get('nps_aggregate', SUPERUSER_USERNAME)
    rental_th = self.wait_for_xpath("//*[text()='25C']")
    first_month_nps_link = (
        rental_th.find_element_by_xpath('./following-sibling::td/a'))
    assert int(first_month_nps_link.text) == -100
    self.wait_a_sec()
    self.driver.get(first_month_nps_link.get_property('href'))
    assert 5 == int(self.driver.find_element_by_xpath('//td').text)
