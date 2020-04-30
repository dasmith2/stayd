from util.web_test import WebTestCommand
from work.management.commands.clean_test import CleanTest
from work.views.web_tests import CLEAN_CO_OWNER_USERNAME


class Command(WebTestCommand):
  help = (
      'Run this from your local machine to create a new cleaning checklist '
      'and use it to do a cleaning.')

  def web_test_classes(self):
    return [ReviewCleaningTest]


class ReviewCleaningTest(CleanTest):
  def run(self):
    self.open_browser()
    cleaning_checklist_pk = self.create_checklist_pk()
    self.open_cleaning(cleaning_checklist_pk)
    self.clean()
    self.open_review()

  def open_review(self):
    self.logout()
    self.login(CLEAN_CO_OWNER_USERNAME)
    self.driver.find_element_by_link_text('Review').click()
    assert 'Living room!' == (
        self.driver.find_element_by_tag_name('h2').text)
    self.driver.find_element_by_link_text('Back to cleanings').click()
