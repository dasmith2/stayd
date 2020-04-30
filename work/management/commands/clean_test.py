from django.shortcuts import reverse

from util.web_test import WebTestCommand
from work.management.commands.clean_example import CleanExample


class Command(WebTestCommand):
  help = (
      'Run this from your local machine to create a new cleaning checklist '
      'and use it to do a cleaning.')

  def web_test_classes(self):
    return [CleanTest]


class CleanTest(CleanExample):
  def run(self):
    self.open_browser()
    cleaning_checklist_pk = self.create_checklist_pk()
    self.open_cleaning(cleaning_checklist_pk)
    self.clean()

  def clean(self):
    self.wait_for_text('//h2[@class="title"]', 'Living room!')

    # You can report an issue!
    container = self.driver.find_element_by_id('cleaning_ticket_photo')
    self.do_file_upload(container, self.img_path('chicken_in_sink.jpg'))
    theres_a_chicken = 'There\'s literally a chicken in the sink'
    self.driver.find_element_by_id('cleaning_ticket_description').send_keys(
        theres_a_chicken)
    self.driver.find_element_by_id(
        'cleaning_ticket_report_button_wrapper').find_element_by_tag_name(
            'button').click()
    assert theres_a_chicken == self.driver.find_element_by_class_name(
        'ticket_title').text
    # And you can clear it out
    self.driver.find_element_by_class_name('fixed').click()
    assert 0 == len(self.driver.find_elements_by_class_name(
        'ticket_title'))

    container = self.driver.find_element_by_class_name(
        'confirmation_photo_wrapper')
    self.do_file_upload(container, self.img_path('living_room.jpg'))
    self.assert_image_uploaded(container)
    self.driver.find_element_by_class_name('done_checkbox').click()

    container = self.driver.find_elements_by_class_name(
        'confirmation_photo_wrapper')[1]
    self.do_file_upload(container, self.img_path('coffee_confirm.jpg'))
    self.assert_image_uploaded(container)
    self.driver.find_elements_by_class_name('done_checkbox')[1].click()

    # When you click the done slide radio button, it has to do a whole round
    # trip to the server to save the slide. If you click done cleaning
    # immediately, the done slide may not have happened yet, and then server
    # side validation will block the done cleaning click.
    self.driver.find_elements_by_class_name('done_checkbox')[2].click()

    def done_saving():
      for msg in self.driver.find_elements_by_class_name('saved'):
        if msg.is_displayed():
          return False
      return True
    self.wait_for_closure(done_saving)
    self.driver.find_element_by_id('cleaning_done').click()

    assert self.driver.current_url.find(reverse('clean_co_cleanings')) > 0

  def shown_alert_count(self):
    shown = 0
    for alert in self.driver.find_elements_by_class_name('alert'):
      if alert.is_displayed():
        shown += 1
    return shown
