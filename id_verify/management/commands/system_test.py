"""
You can see in guesty/api_getter.py that only prod can write to
Guesty. front/models.py and guest_messages/mandrill.py don't send
messages on stage.

pip install selenium
"""
import os
from pathlib import Path
import requests

from django.shortcuts import reverse
from selenium import webdriver
from selenium.webdriver.common.keys import Keys

from commands.stayd_command import StaydCommand
from guesty.api import sync_reservation


def get_test_guesty_id():
  url = 'https://stage.stayd.com{}'.format(
      reverse('get_reservation_for_system_test'))
  return requests.get(url).json()['guesty_id']


def get_active_element(driver):
  return driver.execute_script('return document.activeElement;')


class Command(StaydCommand):
  help = (
      'Run this from your local machine. '
      'It creates an entirely new ID submission in stage and verifies it.')

  def run(self, verbose):
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
    guesty_id = get_test_guesty_id()
    print('Guesty id: {}'.format(guesty_id))
    res = sync_reservation(guesty_id)
    driver = webdriver.Firefox()
    self._submit_an_id(driver, res)
    self._approve_the_id(driver, res)

  def _submit_an_id(self, driver, res):
    driver.get('https://stage.stayd.com{}?phone={}'.format(
        reverse('verify_id'), res.guest.phone))
    h1 = driver.find_element_by_tag_name('h1')
    assert res.guest.first_name in h1.text
    assert h1.is_displayed()
    driver.find_element_by_xpath('//*[contains(text(),"Get started")]').click()
    use_guest_phone = driver.find_element_by_id('use-guest-phone')
    assert use_guest_phone.is_displayed()
    use_guest_phone.click()
    email = get_active_element(driver)  # Should be email anyway.
    assert 'email' == email.get_attribute('id')
    assert email.is_displayed()
    email.send_keys('test@test.com')
    email.send_keys(Keys.ENTER)

    self._do_file_upload('panel-id', self._img_path('test_id.jpg'), driver)
    if res.cc_photo_required():
      self._do_file_upload('panel-cc', self._img_path('test_cc.jpg'), driver)

    done_button = driver.find_element_by_id('done-button')
    assert done_button.is_displayed()
    done_button.click()
    assert driver.current_url == 'https://stage.stayd.com/verify_id/thanks'

  def _approve_the_id(self, driver, res):
    driver.get('https://stage.stayd.com{}'.format(reverse('submissions')))
    driver.find_element_by_id('id_username').send_keys('systemtest')
    driver.find_element_by_id('id_password').send_keys('97d2mk.Y')
    driver.find_element_by_tag_name('button').click()

    submission_finder = '//div[@data-name="{}"]'.format(res.guest.full_name)
    container = driver.find_element_by_xpath(submission_finder)
    yeses = container.find_elements_by_xpath('//*[@value="yes"]')
    for yes in yeses:
      yes.click()
    driver.find_element_by_xpath('//button[@type="submit"]').click()
    container_exists = len(driver.find_elements_by_xpath(submission_finder))
    assert not container_exists

  def _do_file_upload(self, container_id, img_path, driver):
    id_upload = driver.find_element_by_xpath(
        '//*[@id="{}"]//input'.format(container_id))
    assert id_upload.is_displayed()
    id_upload.send_keys(img_path)
    status = driver.find_element_by_xpath(
        '//*[@id="{}"]//*[@class="box-text"]'.format(container_id))
    assert status.text == 'Success! Thank you :)'
    next_button = driver.find_element_by_xpath(
        '//*[@id="{}"]//*[@class="button"]'.format(container_id))
    assert next_button.is_displayed()
    next_button.click()

  def _img_path(self, img_file_name):
    this_dir = os.path.dirname(os.path.realpath(__file__))
    app_dir = Path(this_dir).parent.parent.parent.as_posix()
    img_dir = os.path.join(app_dir, 'static')
    return os.path.join(img_dir, img_file_name)

  def name(self):
    return 'id_verify system_test'
