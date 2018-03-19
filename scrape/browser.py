PROFILE_PARENT_DIR = 'c:/Users/dave/Desktop/profiles'
PROFILE_DIRECTORY = '{}/3fumajxn.Abe Copy'.format(PROFILE_PARENT_DIR)
TRANSACTIONS_URL = 'https://www.airbnb.com/users/transaction_history'
LIVE_COOKIES_DB = os.path.join(PROFILE_DIRECTORY, 'cookies.sqlite')
MY_COOKIES_DB = os.path.join(PROFILE_PARENT_DIR, 'cookies.sqlite')
GMAIL = 'https://mail.google.com'

# I went into the profile and found the cookies database. This is ALMOST
# an exact copy. I added user_Name TEXT, and added user_name to
# the unique constraint so I can store all user cookies in the same database.
CREATE_COOKIE_TABLE = """
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
  CONSTRAINT moz_uniqueid UNIQUE (user_name, name, host, path, originAttributes));
"""

class Browser(object):
  def __init__(self, user):
    self.user = user
    self.webdriver = None

  def get(self, url):
    return self.webdriver.get(url)

  def find_elements_by_id(self, id):
    return self.webdriver.find_elements_by_id(self, id)

  def find_element_by_id(self, id):
    return self.webdriver.find_element_by_id(id)

  def find_elements_by_xpath(self, xpath):
    return self.webdriver.find_elements_by_xpath(xpath)

  def find_element_by_xpath(self, xpath):
    return self.webdriver.find_element_by_xpath(xpath)

  def close(self):
    self.webdriver.close()
    self._save_cookies()

  def start(self):
    self._set_proxy_stuff()
    self._load_cookies()
    profile = webdriver.FirefoxProfile(PROFILE_DIRECTORY)
    self.webdriver = webdriver.Firefox(profile)
    self._clear_that_dialogue()

  def _clear_that_dialogue(self):
    still_have_that_dialogue = True
    # There's a race here. FF pops up a dialogue asking for the proxy username
    # and password. I THINK what's happening is, if you ff.get BEFORE that dialogue
    # shows up, then the focus is stolen by the browser window and the dialogue
    # literally goes behind the Firefox window and you get
    # WebDriverException: Message: Reached error page: about:neterror?e=netReset
    # &u=http%3A//whatsmyip.org/&c=UTF-8&f=regular
    # &d=The%20connection%20to%20the%20server%20was%20reset%20while%20the%20page
    # %20was%20loading. instead of that UnexpectedAlertPresentException error.
    # It's good when you have that alert error because doing ff.get with a filled
    # in username and password causes the dialogue to go away and we're off to the
    # races.
    time.sleep(1)
    while still_have_that_dialogue:
      try:
        self.webdriver.get('http://whatsmyip.org')
        # This can happen here too when the dialogue is BEHIND the FF window.
        # I tried adding that time.sleep(1) there.
        # 
        still_have_that_dialogue = False
      except UnexpectedAlertPresentException:
        pass

  def _save_cookies(self):
    live_cookies_conn = sqlite3.connect(LIVE_COOKIES_DB)
    my_cookies_conn = sqlite3.connect(MY_COOKIES_DB)
    my_cookies_conn.cursor().execute(CREATE_COOKIE_TABLE)
    my_cookies_conn.cursor().execute(
        'DELETE FROM moz_cookies WHERE user_name = ?;', (self.user.name,))
    live_cookies = live_cookies_conn.cursor().execute(
        'SELECT * FROM moz_cookies;')
    for cookie in live_cookies.fetchall():
      save_cookie_values = (self.user.name,) + cookie[1:]
      my_cookies_conn.cursor().execute((
          'INSERT INTO moz_cookies(user_name, baseDomain, originAttributes, '
          'name, value, host, path, expiry, lastAccessed, creationTime, '
          'isSecure, isHttpOnly, inBrowserElement, sameSite) VALUES '
          '(?,?,?,?,?,?,?,?,?,?,?,?,?,?);'), save_cookie_values)
    my_cookies_conn.commit()
    my_cookies_conn.close()
    live_cookies_conn.close()

  def _load_cookies(self):
    live_cookies_conn = sqlite3.connect(LIVE_COOKIES_DB)
    my_cookies_conn = sqlite3.connect(MY_COOKIES_DB)
    live_cookies_conn.cursor().execute('DELETE FROM moz_cookies;')
    saved_cookies = my_cookies_conn.cursor().execute(
        'SELECT * FROM moz_cookies WHERE user_name = ?;', (self.user.name,))
    for cookie in saved_cookies.fetchall():
      save_cookie_values = cookie[2:]
      live_cookies_conn.cursor().execute((
          'INSERT INTO moz_cookies(baseDomain, originAttributes, '
          'name, value, host, path, expiry, lastAccessed, creationTime, '
          'isSecure, isHttpOnly, inBrowserElement, sameSite) VALUES '
          '(?,?,?,?,?,?,?,?,?,?,?,?,?);'), save_cookie_values)
    live_cookies_conn.commit()
    live_cookies_conn.close()
    my_cookies_conn.close()

  def _set_proxy_stuff(self):
    prefs_js = os.path.join(PROFILE_DIRECTORY, 'prefs.js')
    _set_prefs_js_proxy(prefs_js, self.user.ip, self.user.port)
    logins_json = os.path.join(PROFILE_DIRECTORY, 'logins.json')
    _set_logins_json_proxy(logins_json, self.user.ip, self.user.port)

  def _set_prefs_js_proxy(self, prefs_js_path, new_ip, new_port):
    new_lines = []
    with open(prefs_js_path, 'r') as prefs_js:
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
    with open(prefs_js_path, 'w') as prefs_js:
      for line in new_lines:
        prefs_js.write(line)

  def _set_logins_json_proxy(self, logins_json_path, new_ip, new_port):
    # "hostname":"moz-proxy://198.23.168.220:21288"
    content = open(logins_json_path, 'r').read()
    finder = re.compile(r'"moz-proxy://(\d+\.)+\d+:\d+"')
    new_value = '"moz-proxy://{}:{}"'.format(new_ip, new_port)
    open(logins_json_path, 'w').write(finder.sub(new_value, content))