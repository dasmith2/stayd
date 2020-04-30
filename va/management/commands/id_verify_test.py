"""
pip install selenium
"""
from selenium.webdriver.common.keys import Keys

from va.management.commands.id_verify_example import IDVerifyWebExample
from util.web_test_users import SUPERUSER_USERNAME
from util.web_test import WebTestCommand


class Command(WebTestCommand):
  help = (
      'Run this from your local machine. '
      'It creates an entirely new ID submission on --server and verifies it.')

  def web_test_classes(self):
    return [IDVerifyWebTest]


class IDVerifyHelper(object):
  def __init__(self, web_test):
    self.web_test = web_test
    self.driver = web_test.driver
    self.server = web_test.server

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
    self.web_test.server_get('submissions', SUPERUSER_USERNAME)

    tries = 0
    found = self.approve_id_container_on_page(guest_full_name)
    while not found:
      if tries > 5:
        raise Exception('The submission never showed in the list.')
      tries += 1
      self.wait_a_sec()
      self.web_test.server_get('submissions', SUPERUSER_USERNAME)
      found = self.approve_id_container_on_page(guest_full_name)
    return found


class IDVerifyWebTest(IDVerifyWebExample):
  def run(self):
    """
    Ask stage to get some upcoming reservation from Guesty with a checkin in
    the upcoming month, clear out any existing submissions, and return the
    guesty id.
    Sync that reservation locally.
    Pop open selenium.
    Go to https://stage.stayd.com/verify_id/ for that reservation.
    Complete the id submission.
    Log into https://stage.stayd.com/verify_id/submissions with
    username: systemtest password: 97d2mk.Y
    Approve the submission.
    Verify that it's not in the list any more.
    """
    self.open_id_verify()
    helper = IDVerifyHelper(self)
    self._submit_an_id(helper)
    helper.approve_id(self.guest_full_name)

  def _submit_an_id(self, helper):
    """ We auto scroll the page for the user. If you go so fast that you
    get two scroll animations at the same time, the page jumps frantically and
    the test is a mess to watch. Ideally these tests verify but also reasure.
    So just put a bit of sleep on navigation events. """
    h1 = self.driver.find_element_by_tag_name('h1')
    assert self.guest_first_name in h1.text
    assert h1.is_displayed()
    helper.click_get_started()
    use_guest_phone = helper.use_guest_phone()
    assert use_guest_phone.is_displayed()
    use_guest_phone.click()
    self.wait_a_sec()
    email = self.get_active_element()  # Should be email anyway.
    assert 'email' == email.get_attribute('id')
    assert email.is_displayed()
    helper.enter_email('test@test.com')

    helper.do_file_upload('panel-id', self.img_path('ny_id_front.jpg'))
    self.click_button('panel-id')

    helper.done()
