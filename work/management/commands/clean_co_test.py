from util.web_test import WebTestCommand
from work.management.commands.clean_co_example import CleanCoExample


class Command(WebTestCommand):
  help = (
      'Run this from your local machine to create a few cleanings for a '
      'cleaning company and open a web page where you can assign cleanings, '
      'and run a few tests.')

  def web_test_classes(self):
    return [CleanCoTest]


class CleanCoTest(CleanCoExample):
  def run(self):
    self.get_a_bunch_of_cleanings()
    self.open_browser()

    line_item_text = 'Took in the reality of the situation'

    # Create a new cleaning on 12/25/2018
    self.driver.find_element_by_link_text('Create new cleaning').click()
    self.driver.find_element_by_id('id_day').send_keys('2018-12-25')
    self.wait_a_sec()
    self.driver.find_element_by_id('id_started_at').send_keys('11:15:00')
    self.wait_a_sec()
    self.driver.find_element_by_id('id_completed_at').send_keys('14:05:00')
    self.wait_a_sec()
    self.driver.find_element_by_xpath(
        '//select[@id="id_assigned_to"]/option[text()="Bob Slob"]').click()
    self.wait_a_sec()
    self.driver.find_element_by_id('id_li-0-amount').send_keys('10')
    self.wait_a_sec()
    self.driver.find_element_by_id('id_li-0-description').send_keys(
        line_item_text)
    self.wait_a_sec()
    self.driver.find_element_by_xpath('//input[@value="Save"]').click()
    self.wait_a_sec()
    self.driver.find_element_by_link_text('Back to list').click()

    # Find it in the list
    self.driver.find_element_by_id('from_date').clear()
    self.driver.find_element_by_id('from_date').send_keys('12/25/2018')
    self.wait_a_sec()
    self.driver.find_element_by_id('to_date').clear()
    self.driver.find_element_by_id('to_date').send_keys('12/26/2018')
    self.wait_a_sec()
    self.driver.find_element_by_id('report').click()
    # ($95 flat fee + $10 line item) * 1.1 from sales tax
    self.driver.find_element_by_xpath('//td[text()="$115.50"]')
    self.driver.find_element_by_xpath('//td[text()="COMPLETE"]')
    self.wait_a_sec()

    # "Edit" it
    self.driver.find_element_by_link_text('Edit').click()
    got_line_item_text = self.driver.find_element_by_id(
        'id_li-0-description').get_attribute('value')
    assert got_line_item_text == line_item_text
    self.driver.find_element_by_xpath('//input[@value="Save"]').click()
    self.wait_a_sec()
    self.driver.find_element_by_link_text('Back to list').click()
    self.wait_a_sec()

    # Reopen a canceled cleaning
    self.driver.find_element_by_xpath(
        '//td[text()="CANCELED"]/..//td/a[text()="Edit"]').click()
    self.driver.find_element_by_xpath(
        '//input[@value="This cleaning actually happened"]').click()
    self.driver.find_element_by_id('id_started_at').send_keys('11:15:00')
    self.wait_a_sec()
    self.driver.find_element_by_id('id_completed_at').send_keys('14:05:00')
    self.wait_a_sec()
    self.driver.find_element_by_xpath('//input[@value="Save"]').click()
    self.driver.find_element_by_link_text('Back to list').click()

    # Assign a cleaner in the first drop down list. One time, there were extra
    # cleanings in this list and the second drop down was the one I wanted. I
    # suspect that's a bug in _clear_out_old_web_test_cleanings that's still
    # out there.
    clarance = self.driver.find_element_by_xpath(
        '//select/option[text()="Very Clean Clarance"]')
    assert not clarance.is_selected()
    clarance.click()
    # And make sure it sticks.
    self.driver.refresh()
    clarance = self.driver.find_element_by_xpath(
        '//select/option[text()="Very Clean Clarance"]')
    assert clarance.is_selected()

    self.driver.find_element_by_link_text('Cleaners').click()
    self.driver.find_element_by_link_text('Add a new cleaner').click()
    self.driver.find_element_by_id('id_name').send_keys('Car Ballet')
    self.driver.find_element_by_id('id_phone').send_keys('(123)456-7890')
    self.driver.find_element_by_id('id_email').send_keys('car@ballet.com')
    self.driver.find_element_by_xpath('//input[@value="Save"]').click()
    self.wait_for_text('//tbody', 'Car Ballet')
