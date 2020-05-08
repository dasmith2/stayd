from selenium.webdriver.common.keys import Keys

from util.channels import AIRBNB
from util.web_test_users import VIRTUAL_HOST_USERNAME


class IDVerifyHelper(object):
  def __init__(self, web_test):
    self.web_test = web_test
    self.driver = web_test.driver
    self.server = web_test.server

  def open_id_verify(self, channel=AIRBNB):
    self.get_test_reservation(channel=channel)
    self.web_test.get('{}?id={}'.format(
        self.web_test.server_reverse('verify_id'), self.channel_id))

  def get_test_reservation(self, channel=AIRBNB):
    got = self.web_test.server_json(
        'get_reservation_for_id_verify_test', channel=channel)
    self.channel_id = got['channel_id']
    self.guest_first_name = got['guest_first_name']
    self.guest_full_name = got['guest_full_name']

  def wait_a_sec(self):
    self.web_test.wait_a_sec()

  def click_get_started(self):
    self.wait_a_sec()
    self.driver.find_element_by_xpath(
        '//*[contains(text(),"Get started")]').click()
    self.wait_a_sec()

  def use_guest_phone(self):
    return self.driver.find_element_by_id('use-guest-phone')

  def enter_email(self, email_address):
    email = self.driver.find_element_by_id('email')
    email.send_keys(email_address)
    self.wait_a_sec()
    email.send_keys(Keys.ENTER)
    self.wait_a_sec()

  def do_file_upload(self, container_id, img_path):
    id_upload = self.driver.find_element_by_xpath(
        '//*[@id="{}"]//input'.format(container_id))
    # Selenium is a bit of a mess. xpath ../* means this exact same element. On
    # one computer, id_upload.is_displayed() is True, but on another, it's
    # False. On both computers the parent div is visible.
    assert id_upload.find_element_by_xpath('../../*').is_displayed()
    id_upload.send_keys(img_path)
    status_xpath = '//*[@id="{}"]//*[@class="box_text"]'.format(container_id)
    self.web_test.wait_for_text(status_xpath, 'Success! Thank you :)')

  def done(self):
    self.web_test.click_button('done-button')
    tries = 0
    while self.driver.current_url != self.web_test.server_reverse(
        'thanks_for_verifying_id'):
      if tries == 10:
        raise Exception('Never got to the thanks page')
      tries += 1
      self.wait_a_sec()
    self.wait_a_sec()

  def approve_id_container_on_page(self, guest_full_name):
    submission_finder = '//div[@data-name="{}"]'.format(guest_full_name)
    looking = self.driver.find_elements_by_xpath(submission_finder)
    if len(looking):
      return looking[0]

  def approve_id(self, guest_full_name):
    container = self.get_approve_id_container(guest_full_name)

    for radio in container.find_elements_by_class_name('maybe_show_the_rest'):
      if radio.get_attribute('value') == 'yes':
        radio.click()
        self.wait_a_sec()

    # Now the rest of the fields should be visible
    has_negative_finder = (
        './/*[@value="no" and contains(@name,"_has_negative_reviews")]')
    container.find_element_by_xpath(has_negative_finder).click()
    container.find_element_by_xpath('.//*[@type="number"]').send_keys(7)
    book_for_finder = (
        './/*[@value="yes" and contains(@name,"_booking_for_themself")]')
    container.find_element_by_xpath(book_for_finder).click()
    described_finder = (
        './/*[@value="yes" and contains(@name,"_explained_trip")]')
    container.find_element_by_xpath(described_finder).click()
    lives_nearby_finder = (
        './/*[@value="no" and contains(@name,"_lives_nearby")]')
    container.find_element_by_xpath(lives_nearby_finder).click()

    container.find_element_by_xpath('.//*[@type="date"]').send_keys(
        '1978-08-31')

    # a.k.a. background checks
    full_names = container.find_elements_by_xpath(
        './/*[@type="text"]')
    if len(full_names):
      full_names[0].send_keys('Michael M Motorist')
      photo_count = len(container.find_elements_by_class_name('one_third'))
      type_finder = './/*[@value="passport"]'
      if photo_count == 3:
        type_finder = './/*[@value="us_id_front_and_back"]'
      container.find_element_by_xpath(type_finder).click()

    self.wait_a_sec()
    self.driver.find_element_by_xpath('//button[@type="submit"]').click()
    self.wait_a_sec()

    assert not self.approve_id_container_on_page(guest_full_name)

  def get_approve_id_container(self, guest_full_name):
    self.web_test.server_get('submissions', VIRTUAL_HOST_USERNAME)

    tries = 0
    found = self.approve_id_container_on_page(guest_full_name)
    while not found:
      if tries > 5:
        raise Exception('The submission never showed in the list.')
      tries += 1
      self.wait_a_sec()
      self.web_test.server_get('submissions', VIRTUAL_HOST_USERNAME)
      found = self.approve_id_container_on_page(guest_full_name)
    return found
