import time

from util.web_test import WebTest, WebTestCommand
from work.views.web_tests import CLEANING_ADMINISTRATOR_USERNAME


class Command(WebTestCommand):
  help = (
      'Run this from your local machine to create a new cleaning checklist.')

  def web_test_classes(self):
    return [CleaningChecklistTest]


class CleaningChecklistTest(WebTest):
  """ There's no need to put this in util/management/commands/web_tests.py
  because CleanTest inherits from this test and does all the same stuff plus
  more. """
  def run(self):
    self.open_browser()
    self.create_checklist_pk()

  def assert_image_uploaded(self, container):
    seconds = 0
    while 0 == len(
        container.find_elements_by_class_name('file_upload_overlay')):
      if seconds == 6:
        raise Exception('The example image never showed up')
      time.sleep(1)
      seconds += 1

  def create_checklist_pk(self):
    self.driver.find_element_by_id('id_title').send_keys('Slate 1 bdrm')
    self.driver.find_element_by_id('submit_new_checklist').click()

    # Now we're on the checklist edit page.
    self.wait_for_class('new_slide_title').send_keys('Living room')
    self.driver.find_element_by_class_name('new_slide').click()
    self.driver.find_element_by_xpath('//input[@value="Living room"]')
    self.driver.find_element_by_class_name('new_step_title').send_keys(
        'Polish the remote buttons')
    self.driver.find_element_by_class_name('add_step').click()
    container = self.driver.find_element_by_class_name('img')
    self.do_file_upload(container, self.img_path('living_room.jpg'))
    self.assert_image_uploaded(container)

    # You can edit text!
    self.driver.find_element_by_id('checklist_title').send_keys('!')
    self.driver.find_element_by_class_name('slide_title').send_keys('!')
    self.driver.find_element_by_class_name('step_text').send_keys('!')

    self.driver.find_elements_by_tag_name('h1')[-1].click()
    self.wait_a_sec()
    self.driver.refresh()
    assert 'Slate 1 bdrm!' == (
        self.driver.find_element_by_id(
            'checklist_title').get_attribute('value'))

    # The page is being populated with an ajax type situation.
    self.wait_for_xpath('//input[@value="Living room!"]')

    self.driver.find_element_by_xpath(
        '//input[@value="Polish the remote buttons!"]')

    # You can remove steps and slides
    self.driver.find_element_by_class_name('new_slide_title').send_keys(
        'Bathroom')
    self.driver.find_element_by_class_name('new_slide').click()
    self.driver.find_element_by_class_name('new_step_title').send_keys(
        'Wring out the bathmat')
    self.driver.find_element_by_class_name('add_step').click()
    assert 2 == len(self.driver.find_elements_by_class_name('step'))
    self.driver.find_element_by_class_name('delete_step').click()
    assert 1 == len(self.driver.find_elements_by_class_name('step'))
    assert 2 == len(self.driver.find_elements_by_class_name('slide'))
    self.driver.find_element_by_class_name('delete_slide').click()
    assert 1 == len(self.driver.find_elements_by_class_name('slide'))

    # Add in a coffee step so clean_test has 2 slides to work with
    self.driver.find_element_by_class_name('new_slide_title').send_keys(
        'Coffee')
    self.driver.find_element_by_class_name('new_slide').click()
    self.driver.find_element_by_class_name('new_step_title').send_keys(
        'Drink the leftover coffee')
    self.driver.find_element_by_class_name('add_step').click()
    self.driver.find_element_by_class_name('new_step_title').send_keys(
        'Arrange things pleasantly')
    self.driver.find_element_by_class_name('add_step').click()
    container = self.driver.find_element_by_class_name('img')
    self.do_file_upload(container, self.img_path('coffee.jpg'))
    self.assert_image_uploaded(container)

    # You can move slides
    top_title = self.driver.find_element_by_class_name(
        'slide_title').get_attribute('value')
    assert 'Coffee' == top_title
    self.driver.find_element_by_class_name('move_down').click()
    top_title = self.driver.find_element_by_class_name(
        'slide_title').get_attribute('value')
    assert 'Living room!' == top_title

    # Add a final slide with no required photo.
    self.driver.find_elements_by_class_name('new_slide_title')[-1].send_keys(
        'DON\'T photograph anything')
    self.driver.find_elements_by_class_name('new_slide')[-1].click()

    return int(
        self.driver.find_element_by_id('checklist_pk').get_attribute('value'))

  def open_browser(self):
    self.server_json('clear_out_cleaning_checklists')
    self.server_get('new_checklist', CLEANING_ADMINISTRATOR_USERNAME)
