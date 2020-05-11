from datetime import date
import time

from util.web_test import WebTestCommand
from work.management.commands.cleaning_checklist_test import (
    CleaningChecklistTest)
from work.views.web_tests import CLEAN_CO_OWNER_USERNAME, CLEAN_CO_BOB_USERNAME


class Command(WebTestCommand):
  help = (
      'Run this from your local machine to create a new cleaning checklist '
      'and use it to do a cleaning.')

  def web_test_classes(self):
    return [CleanExample]


class CleanExample(CleaningChecklistTest):
  def run(self):
    self.open_browser()
    cleaning_checklist_pk = self.create_checklist_pk()
    self.open_cleaning(cleaning_checklist_pk)

  def get_a_bunch_of_cleanings(self, cleaning_checklist_pk):
    """ And return one example cleaning pk """
    return self.server_json(
        'get_a_bunch_of_cleanings_for_web_tests',
        cleaning_checklist_pk=cleaning_checklist_pk)['example_cleaning_pk']

  def open_cleaning(self, cleaning_checklist_pk, demo_mode=False):
    import pdb

    def pause(seconds):
      if demo_mode:
        time.sleep(seconds)

    cleaning_pk = self.get_a_bunch_of_cleanings(cleaning_checklist_pk)
    self.server_get('clean_co_cleanings', CLEAN_CO_OWNER_USERNAME)
    pause(3)

    todays_cleaning_row = self.driver.find_element_by_xpath(
        '//*[text()="{}"]/..'.format(str(date.today())))
    action_cell = todays_cleaning_row.find_element_by_tag_name('td')
    # Just double checking that cleaning_pk is for today's cleaning
    assert action_cell.get_attribute('clean_url').find(str(cleaning_pk)) > 0
    # Assign it to Bob.
    todays_cleaning_row.find_element_by_xpath(
        './/option[text()="Bob Slob"]').click()
    if demo_mode:
      pdb.set_trace()
    else:
      self.wait_a_sec()
    self.logout()
    pause(2)
    self.login(CLEAN_CO_BOB_USERNAME)
    if demo_mode:
      pdb.set_trace()
    else:
      self.wait_a_sec()
    self.driver.find_element_by_link_text('Clean').click()
