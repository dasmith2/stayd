"""
Web tests are supposed to make it really easy to see that a web page still
works. We should have them for any web page that, were it to go down, would
also bring the company down. For instance, if the id verification flow broke,
we'd be pretty screwed. So there's a web test for that.

pip install selenium  # Intentionally not pipenv

Selenium runs only on local development environments, so never include this
file in a tests.py file, say, because those must run on stage as part of
continuous integration. Also don't pipenv install selenium because that would
cause selenium to be installed on stage and production.

id_verify/management/commands/id_verify_test.py is an example web test. You
can run it with ./manage.py id_verify_test

bgcheck/management/commands/bgcheck_example.py is an example helpful demo page.

util/management/commands/web_tests.py runs all the web tests.
"""
from abc import abstractmethod
import os
from pathlib import Path
import pdb
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.shortcuts import reverse
import requests
from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException, SessionNotCreatedException)
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions

from util.html_status_codes import is_server_error
from util.web_test_users import SAME_PASSWORD
from util.urls import date_to_url_str


class WebTest(object):
  """ This is a base class for running tests with Selenium. """
  def __init__(self, server=None, demo_mode=None):
    self.server = server or self.default_server()
    self.demo_mode = demo_mode
    self.driver = None

  def turn_on_debugger(self, message):
    print(message)
    pdb.set_trace()

  def pre_run(self):
    self.driver = webdriver.Firefox()

  def close_driver(self):
    if self.driver:
      try:
        self.wait_a_sec()
        self.driver.close()
      except SessionNotCreatedException:
        # The driver is closed already.
        pass

  @abstractmethod
  def run(self):
    raise NotImplementedError('run')

  def get(self, url):
    self.driver.get(url)
    self.close_django_toolbar()

  def close_django_toolbar(self):
    # The debug toolbar gets in the way of elements when you try to click on
    # them sometimes.
    try:
      toolbar = self.driver.find_element_by_id('djDebugToolbar')
      if toolbar.value_of_css_property('display') == 'block':
        self.driver.find_element_by_id('djHideToolBarButton').click()
    except NoSuchElementException:
      pass

  def default_server(self):
    # return settings.STAGE_SERVER is also a common one. Or you can just do
    # ./manage.py my_web_test --server=https://stage.hihoward.com
    return 'http://127.0.0.1:8000'

  def logout(self):
    self.driver.find_element_by_id('logout_link').click()

  def server_get(
      self, view_name, username, password=SAME_PASSWORD, query_string='',
      **kwargs):
    """ You can find a bunch of useful usernames in util/web_test_users.py """
    url = self.server_reverse(view_name, **kwargs)
    if query_string:
      if query_string[0] != '?':
        url += '?'
      url += query_string
    self.get(url)
    if username:
      if bool(len(self.driver.find_elements_by_id('id_username'))):
        self.login(username, password)
      else:
        current_usernames = self.driver.find_elements_by_id('current_username')
        if current_usernames and current_usernames[0].text != username:
          self.logout()
          self.get(url)
          self.login(username, password)
    self.raise_if_on_error_screen()

  def dated_report_get(self, view_name, from_date, to_date):
    self.server_get(
        view_name, from_date_str=date_to_url_str(from_date),
        to_date_str=date_to_url_str(to_date))

  def server_json(self, view_name, *args, **kwargs):
    response = requests.get(self.server_reverse(view_name, *args, **kwargs))
    if is_server_error(response):
      if self.server == 'http://127.0.0.1:8000':
        raise Exception('Server error. Look at your ./manage.py runserver')
      raise Exception('Server error. Check {}/admin/errors/stayderror/'.format(
          self.server))
    return response.json()

  def server_reverse(self, view_name, *args, **kwargs):
    path = reverse(view_name, args=args, kwargs=kwargs)
    return '{}{}'.format(self.server, path)

  def wait_for_closure(self, closure, error_message=None):
    attempts = 0
    while attempts < 5 and not closure():
      time.sleep(1)
      attempts += 1
    if not closure():
      raise Exception(error_message or 'Closure was never True')

  def wait_for_class(self, class_name):
    WebDriverWait(self.driver, 10).until(
        expected_conditions.presence_of_element_located(
            (By.CLASS_NAME, class_name)))
    return self.driver.find_element_by_class_name(class_name)

  def wait_for_xpath(self, xpath):
    WebDriverWait(self.driver, 10).until(
        expected_conditions.presence_of_element_located(
            (By.XPATH, xpath)))
    return self.driver.find_element_by_xpath(xpath)

  def wait_for_text(self, xpath, expected_text):
    WebDriverWait(self.driver, 10).until(
        expected_conditions.text_to_be_present_in_element(
            (By.XPATH, xpath), expected_text))
    return self.driver.find_element_by_xpath(xpath)

  def wait_a_sec(self):
    time.sleep(1)
    # It's possible they just clicked a button and the page submitted or
    # something and an error screen came up.
    self.raise_if_on_error_screen()

  def raise_if_on_error_screen(self):
    if 1 == len(self.driver.find_elements_by_id('traceback')):
      message = 'There\'s an on-screen Django error. '
      if settings.LOCAL:
        message += 'Check your ./manage.py runserver. '
      else:
        message += 'Check for server error emails from {}. '.format(
            settings.THIS_SERVERS_BASE_URL)
      message += 'The error message is: {}'.format(
          self.driver.find_element_by_xpath('//div[@id="summary"]/pre').text)
      raise Exception(message)

  def click_button(self, container_or_button_id):
    try:
      button = self.driver.find_element_by_xpath(
          '//*[@id="{}"]//*[@class="button"]'.format(container_or_button_id))
    except NoSuchElementException:
      button = self.driver.find_element_by_xpath(
          '//*[@id="{}"]'.format(container_or_button_id))
    assert button.is_displayed()
    button.click()
    self.wait_a_sec()

  def get_active_element(self):
    return self.driver.execute_script('return document.activeElement;')

  def login(self, username, password=SAME_PASSWORD):
    self.wait_a_sec()  # For display purposes
    # Firefox apparently now stays logged in between test runs.
    if self.driver.find_elements_by_id('id_username'):
      self.driver.find_element_by_id(
          'id_username').send_keys(username)
      self.driver.find_element_by_id(
          'id_password').send_keys(password)
      # Tests are supposed to inspire confidence. Pause for a moment rather
      # than blazing through and making the tester feel like they have no idea
      # what just happened.
      self.wait_a_sec()  # For display purposes
      self.driver.find_element_by_tag_name('button').click()
    self.close_django_toolbar()

  def screen_height(self):
    return self.driver.execute_script('return window.screen.height;')

  def scrolled_to(self):
    return self.driver.execute_script('return window.pageYOffset;')

  def is_scrolled_to(self, element):
    scrolled_to = self.scrolled_to()
    screen_height = self.screen_height()
    above = scrolled_to < element.location['y']
    below = scrolled_to + screen_height >= element.location['y']
    return above and below

  def img_path(self, img_file_name):
    this_dir = os.path.dirname(os.path.realpath(__file__))
    app_dir = Path(this_dir).parent.as_posix()
    img_dir = os.path.join(app_dir, 'static')
    return os.path.join(img_dir, img_file_name)

  def do_file_upload(self, container, img_path):
    id_upload = container.find_element_by_xpath('.//input[@type="file"]')
    id_upload.send_keys(img_path)


class WebTestCommand(BaseCommand):
  """ This is a base class for creating manage.py commands that run a web test.
  """
  def handle(self, *args, **options):
    server = options.get('server', None)
    demo_mode = options.get('demo', False)
    web_test_instance = None
    start_with = options.get('start_with', None)
    first_test = True
    for web_test_class in self.web_test_classes():
      if not first_test:
        web_test_instance.close_driver()
      web_test_instance = web_test_class(server=server, demo_mode=demo_mode)
      test_name = web_test_instance.__class__.__module__
      if first_test and start_with and test_name.find(start_with) == -1:
        print('Skipping {}'.format(test_name))
      else:
        print(test_name)
        web_test_instance.pre_run()
        web_test_instance.run()
        print('Success!')
        first_test = False

  def add_arguments(self, parser):
    parser.add_argument(
        '--server', help='What server would you like to run this test on?')
    parser.add_argument('--demo', action='store_true', help=(
        'Some tests have a demo mode which is helpful for showing off '
        'features'))
    parser.add_argument('--start_with', help=(
        'If this command runs more than one web test, jump into the middle of '
        'the webtests starting with the first test whose name contains this '
        'argument.'))
