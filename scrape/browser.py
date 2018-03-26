import logging
import os
import re
import time

from selenium import webdriver
from selenium.common.exceptions import (
    UnexpectedAlertPresentException, WebDriverException,
    SessionNotCreatedException)
import sqlite3
from django.conf import settings


# On my windows machine set this in local_settings.py
# SCRAPE_DIR = 'c:/Users/dave/Desktop/stayd/scrape'
PROFILE_DIR = '{}/3fumajxn.GenericFFProfile'.format(
    settings.SCRAPE_DIR)
CURRENT_USER_COOKIES_DB = os.path.join(
    PROFILE_DIR, 'cookies.sqlite')
ALL_USER_COOKIES_DB = os.path.join(
    PROFILE_DIR, 'all_user_cookies.sqlite')

GMAIL = 'https://mail.google.com'
TRANSACTIONS_URL = 'https://www.airbnb.com/users/transaction_history'


WEBSITE_DOWN = 'WEBSITE_DOWN'
OK = 'OK'
ERROR = 'ERROR'
NO_BROWSER = 'NO_BROWSER'

# I went into the profile and found the cookies database. This is ALMOST
# an exact copy. I added user_Name TEXT, and added user_name to
# the unique constraint so I can store all airvatar cookies in the same
# database.
CREATE_ALL_USERS_COOKIE_TABLE = """
CREATE TABLE IF NOT EXISTS moz_cookies (
  id INTEGER PRIMARY KEY,
  user_name TEXT,
  baseDomain TEXT,
  originAttributes TEXT NOT NULL DEFAULT '',
  name TEXT,
  value TEXT,
  host TEXT,
  path TEXT,
  expiry INTEGER,
  lastAccessed INTEGER,
  creationTime INTEGER,
  isSecure INTEGER,
  isHttpOnly INTEGER,
  inBrowserElement INTEGER DEFAULT 0,
  sameSite INTEGER,
  CONSTRAINT moz_uniqueid UNIQUE (
      user_name, name, host, path, originAttributes));
"""

# This is an exact copy of the standard Firefox cookies database.
CREATE_STANDARD_COOKIE_TABLE = """
CREATE TABLE IF NOT EXISTS moz_cookies (
  id INTEGER PRIMARY KEY,
  baseDomain TEXT,
  originAttributes TEXT NOT NULL DEFAULT '',
  name TEXT,
  value TEXT,
  host TEXT,
  path TEXT,
  expiry INTEGER,
  lastAccessed INTEGER,
  creationTime INTEGER,
  isSecure INTEGER,
  isHttpOnly INTEGER,
  inBrowserElement INTEGER DEFAULT 0,
  sameSite INTEGER,
  CONSTRAINT moz_uniqueid UNIQUE (name, host, path, originAttributes));
"""


class Browser(object):
  def __init__(self, airvatar):
    self.airvatar = airvatar
    self._webdriver = None

  def start(self):
    self._set_proxy_stuff()
    self._load_cookies()
    profile = webdriver.FirefoxProfile(PROFILE_DIR)
    self._webdriver = webdriver.Firefox(profile)
    return self._clear_that_dialogue()

  def close(self):
    self._webdriver.close()

  def get_until_class_name(self, url, wait_for_class_name):
    while True:
      if len(self.find_elements_by_class_name(wait_for_class_name)):
        return OK
      got = self.get(url, always_reload=True)
      if not got == OK:
        return got
      time.sleep(5)

  def get(self, url, always_reload=False):
    if always_reload:
      pass
    else:
      try:
        if self.current_url() == url:
          return OK
      except SessionNotCreatedException:
        return NO_BROWSER

    times = 0
    max_times = 3
    while times < max_times:
      try:
        self._webdriver.get(url)
        self._save_cookies()
        return OK
      except WebDriverException as err:
        times += 1
        more_times = max_times - times
        if more_times > 0:
          logging.warning((
              'Loading {} failed. I\'ll try again {} time{}.').format(
                  url, more_times, 's' if more_times > 1 else ''))
        else:
          logging.error((
              'Loading {} failed {} times with {}You\'ll have to '
              'try again later.').format(url, max_times, err))
        # This is a failure to establish a secure connection and it happens
        # instantly. In that case, wait a second rather than just failing 3
        # times in a row really fast.
        if str(err).find('e=nssFailure2'):
          time.sleep(1)
      except SessionNotCreatedException:
        return NO_BROWSER

    return WEBSITE_DOWN

  def current_url(self):
    return self._webdriver.current_url

  def find_elements_by_id(self, id):
    return self._webdriver.find_elements_by_id(id)

  def find_element_by_id(self, id):
    return self._webdriver.find_element_by_id(id)

  def find_elements_by_xpath(self, xpath):
    return self._webdriver.find_elements_by_xpath(xpath)

  def find_element_by_xpath(self, xpath):
    return self._webdriver.find_element_by_xpath(xpath)

  def find_element_by_class_name(self, class_name):
    return self._webdriver.find_element_by_class_name(class_name)

  def find_elements_by_class_name(self, class_name):
    return self._webdriver.find_elements_by_class_name(class_name)

  def find_element_by_tag_name(self, tag_name):
    return self._webdriver.find_element_by_tag_name(tag_name)

  def find_elements_by_tag_name(self, tag_name):
    return self._webdriver.find_elements_by_tag_name(tag_name)

  def _set_proxy_stuff(self):
    template_prefs_js = os.path.join(PROFILE_DIR, 'template_prefs.js')
    live_prefs_js = os.path.join(PROFILE_DIR, 'prefs.js')
    self._set_prefs_js_proxy(
        template_prefs_js, live_prefs_js, self.airvatar.ip, self.airvatar.port)
    template_logins_json = os.path.join(PROFILE_DIR, 'template_logins.json')
    live_logins_json = os.path.join(PROFILE_DIR, 'logins.json')
    self._set_logins_json_proxy(
        template_logins_json, live_logins_json, self.airvatar.ip,
        self.airvatar.port)

  def _set_prefs_js_proxy(
      self, template_prefs_js_path, live_prefs_js_path, new_ip, new_port):
    new_lines = []
    with open(template_prefs_js_path, 'r') as prefs_js:
      line = prefs_js.readline()
      while line:
        # user_pref("network.proxy.http", "198.23.168.220");
        # user_pref("network.proxy.http_port", 21288);
        ip_pattern = r'(\d+)\.(\d+)\.(\d+)\.(\d+)'
        ip_finder = re.compile(r'proxy.+"{}"'.format(ip_pattern))
        port_finder = re.compile(r'proxy.+port"')
        if ip_finder.search(line):
          line = re.compile(ip_pattern).sub(new_ip, line)
        elif port_finder.search(line):
          line = re.compile(r'\d+').sub(str(new_port), line)
        new_lines.append(line)
        line = prefs_js.readline()
    with open(live_prefs_js_path, 'w') as prefs_js:
      for line in new_lines:
        prefs_js.write(line)

  def _set_logins_json_proxy(
      self, template_logins_json, live_logins_json, new_ip, new_port):
    # ..."hostname":"moz-proxy://198.23.168.220:21288"...
    content = open(template_logins_json, 'r').read()
    finder = re.compile(r'"moz-proxy://(\d+\.)+\d+:\d+"')
    new_value = '"moz-proxy://{}:{}"'.format(new_ip, new_port)
    open(live_logins_json, 'w').write(finder.sub(new_value, content))

  def _load_cookies(self):
    current_user_cookies_conn = self._get_current_user_cookies_conn()
    all_users_cookies_conn = self._get_all_users_cookies_conn()
    current_user_cookies_conn.cursor().execute('DELETE FROM moz_cookies;')
    saved_cookies = all_users_cookies_conn.cursor().execute(
        'SELECT * FROM moz_cookies WHERE user_name = ?;', (
            self.airvatar.name,))
    for cookie in saved_cookies.fetchall():
      save_cookie_values = cookie[2:]
      current_user_cookies_conn.cursor().execute((
          'INSERT INTO moz_cookies(baseDomain, originAttributes, '
          'name, value, host, path, expiry, lastAccessed, creationTime, '
          'isSecure, isHttpOnly, inBrowserElement, sameSite) VALUES '
          '(?,?,?,?,?,?,?,?,?,?,?,?,?);'), save_cookie_values)
    current_user_cookies_conn.commit()
    current_user_cookies_conn.close()
    all_users_cookies_conn.close()

  def _save_cookies(self):
    all_users_cookies_conn = self._get_all_users_cookies_conn()
    domains = set(c['domain'] for c in self._webdriver.get_cookies())
    if len(domains) == 0:
      raise Exception('There are no cookies to save.')
    domain = list(domains)[0]
    if len(domains) > 1 or domain[0] != '.':
      raise Exception((
          'Not sure how to handle anything different from 1 cookie domain '
          'with a leading "." Got {}').format(domains))
    base_domain = domain[1:]
    all_users_cookies_conn.cursor().execute(
        'DELETE FROM moz_cookies WHERE user_name = ? AND baseDomain = ?;', (
            self.airvatar.name, base_domain))
    for cookie in self._webdriver.get_cookies():
      example_last_accessed = 1516221074849359
      example_creation_time = 1511294393466375
      # The only non-self-explanatory one is that the host column corresponds
      # to cookie['domain'].
      all_users_cookies_conn.cursor().execute((
          'INSERT INTO moz_cookies(user_name, baseDomain, originAttributes, '
          'name, value, host, path, expiry, lastAccessed, creationTime, '
          'isSecure, isHttpOnly, inBrowserElement) VALUES '
          '(?,?,?,?,?,?,?,?,?,?,?,?,?);'), (
          self.airvatar.name, base_domain, '', cookie['name'],
          cookie['value'], cookie['domain'], cookie['path'], cookie['expiry'],
          example_last_accessed, example_creation_time, cookie['secure'],
          cookie['httpOnly'], 0))
    all_users_cookies_conn.commit()
    all_users_cookies_conn.close()

  def _get_all_users_cookies_conn(self):
    all_users_cookies_conn = sqlite3.connect(ALL_USER_COOKIES_DB)
    all_users_cookies_conn.cursor().execute(CREATE_ALL_USERS_COOKIE_TABLE)
    return all_users_cookies_conn

  def _get_current_user_cookies_conn(self):
    this_user_cookies_conn = sqlite3.connect(CURRENT_USER_COOKIES_DB)
    this_user_cookies_conn.cursor().execute(CREATE_STANDARD_COOKIE_TABLE)
    return this_user_cookies_conn

  def _clear_that_dialogue(self):
    still_have_that_dialogue = True
    # FF pops up a dialogue asking for the proxy username and password.
    # Clearing it is a matter of a) having the proxy stuff all set up properly
    # in prefs.js and logins.json and b) continuing to request URLs until it
    # finally accepts the stored username and password and moves on.
    try_sleeping_next_time = False
    try_different_domain_next_time = False
    while still_have_that_dialogue:
      time.sleep(1)
      try:
        if try_different_domain_next_time:
          self._webdriver.get(TRANSACTIONS_URL)
        else:
          self._webdriver.get('http://whatsmyip.org')
        return True
      except UnexpectedAlertPresentException:
        # This happens when you try to get a url and the proxy login dialogue
        # is still up, which happens every time we start a new browser. You
        # just have to catch it once and try again and it'll go through.
        pass
      except WebDriverException:
        # Not sure about this one. It's a tough one. I think it might be a
        # catch all kind of thing. You might get it if the user grabs focus
        # away from the browser, or the proxy goes down. It doesn't help to
        # retry every second. Maybe it's whatsmyip.org sometimes and you could
        # immediately load a url from a different domain. Anyway, try loading
        # a different domain, then try waiting 15 seconds to try again, then
        # try a different domain again, finally give up.
        if not try_different_domain_next_time:
          try_different_domain_next_time = True
        elif not try_sleeping_next_time:
          try_sleeping_next_time = True
          try_different_domain_next_time = False
          time.sleep(10)
        else:
          return False

  def find_hrefs(self, containing):
    xpath = '//a[contains(@href,\'{}\')]'.format(containing)
    links = self.find_elements_by_xpath(xpath)
    return list(set(link.get_attribute('href') for link in links))

  def find_href_ids(self, part_before_id):
    id_finder = re.compile(r'{}([^/]+)'.format(part_before_id))
    hrefs = self.find_hrefs(part_before_id)
    ids = set(id_finder.search(href).groups()[0] for href in hrefs)
    return list(ids)
