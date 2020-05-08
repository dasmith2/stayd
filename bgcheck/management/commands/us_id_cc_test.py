from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions

from bgcheck.management.commands.bgcheck_example import BGCheckWebExample
from va.management.commands.id_verify_helper import IDVerifyHelper
from util.channels import BOOKINGCOM
from util.web_test_users import VIRTUAL_HOST_USERNAME
from util.web_test import WebTestCommand


class Command(WebTestCommand):
  help = (
      'Run this from your local machine to test that guests can successfully '
      'enter the front and back of a US ID for a background check in addition '
      'to a credit card.')

  def web_test_classes(self):
    return [USIDCCTest]


class USIDCCTest(BGCheckWebExample):
  def run(self):
    res_data = self.get_bg_check_reservation_data(BOOKINGCOM)
    channel_id = res_data['channel_id']
    guest_name = res_data['guest_name']

    helper = IDVerifyHelper(self)

    self.submit_us_id(channel_id, helper)
    helper.approve_id(guest_name)
    self.bg_check(channel_id)

    data = self.server_json('verify_us_id_cc', channel_id=channel_id)
    if not data['valid']:
      raise Exception(data['problem'])

  def submit_us_id(self, channel_id, helper):
    self.open_id_verify(channel_id)

    helper.click_get_started()
    helper.use_guest_phone().click()
    self.wait_a_sec()
    helper.enter_email('test@test.com')
    self.driver.find_element_by_id('consent_button').click()
    self.wait_a_sec()
    self.driver.find_element_by_id('us_id_type').click()
    self.wait_a_sec()
    helper.do_file_upload(
        'panel_id_front_upload', self.img_path('ny_id_front.jpg'))
    helper.do_file_upload(
        'panel_id_back_upload', self.img_path('ny_id_back.jpg'))
    self.click_button('us_id_next_button')
    self.wait_a_sec()
    helper.do_file_upload('panel-cc', self.img_path('realistic_fake_cc.jpg'))
    self.click_button('panel-cc')
    helper.done()

  def bg_check(self, channel_id):
    self.server_get('bgcheck', VIRTUAL_HOST_USERNAME)
    guest_cell = self.driver.find_element_by_class_name('guest_name')
    assert 'Dave Blave' == guest_cell.text
    # You'd think this is what guest_cell.parent was for, but noooo
    tr = guest_cell.find_element_by_xpath('./..')
    assert '' == tr.find_element_by_class_name('passed').text.strip()
    self.wait_a_sec()
    tr.find_element_by_xpath('.//button[@data-value="True"]').click()
    # Selenium, you sure you made this convoluted yet rigid enough? Sheesh.
    # Perfect world: tr.find('.passed').wait_for(TEXT, 'True', 5)
    WebDriverWait(self.driver, 5).until(
        expected_conditions.text_to_be_present_in_element(
            (By.CLASS_NAME, 'passed'), 'True'))
    self.wait_a_sec()
