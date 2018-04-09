from datetime import date, datetime, timedelta
import re
import time

from django.utils.dateparse import parse_date
from djmoney.money import Money
from selenium.common.exceptions import ElementClickInterceptedException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

from scrape.browser import Browser
from scrape.models import (
    Room, Stay, UNKNOWN, NO_AVAILABILITY, SOME_AVAILABILITY, ALL_AVAILABILITY)

RESTART_FF_EVERY_N_REQUESTS = 20

def get_ff():
  ff = Browser()
  ff.start()
  return ff

def start_search(ff):
  url = cities()[0]
  params = UrlExpert()
  url = params.first_page_url(url)
  url = params.first_price_url(url)
  url = params.first_weekend_url(url)
  pick_up_search(ff, url)

def pick_up_search(ff, url=None):
  if not ff.is_started():
    ff.restart()
  if ff.get_window_size()['width'] > 1100:
    ff.set_window_size(768, 848)
  if not url:
    url = ff.current_url()
  if not UrlExpert().validate(url):
    return

  requests_since_restart = 0
  while url:
    # Airbnb has, like, 2 basic display modes depending on browser width.
    # The wider mode loads a big fat Google map.
    ff.get(url)
    requests_since_restart += 1
    create_db_entries_from_page_data(ff)
    url = UrlExpert().next_url(ff)
    if requests_since_restart >= RESTART_FF_EVERY_N_REQUESTS:
      ff.restart()
      requests_since_restart = 0

def page_data(ff):
  room_id_finder = re.compile(r'/rooms/(select/)?([^/?]+)')

  per_nights = ff.find_elements_by_xpath('//*[contains(text(),\'per night\')]')
  for per_night in per_nights:
    links = per_night.find_elements_by_xpath('ancestor::a')
    prices = per_night.find_elements_by_xpath('../../../span[1]/span[2]')
    if links and prices:
      room_id = room_id_finder.search(
          links[0].get_attribute('href')).groups()[1]
      def strip_non_digits(s):
        return re.compile(r'[^\d]').sub('', s)
      price_per_night = strip_non_digits(prices[0].text)
      yield (room_id, price_per_night)

def create_db_entries_from_page_data(ff):
  params = UrlExpert()
  url = ff.current_url()
  data = list(page_data(ff))
  start_str = params._format_date(params.start(url))
  print('{} listings, ${} - ${}, page {} in {} on {}'.format(
      len(data), params.price_min(url), params.price_max(url),
      params.page(url), params.city(url), start_str))
  for (room_id, price_per_night) in data:
    room = Room.objects.get_or_create(
        airbnb_id=room_id, city=params.city(url), availability=UNKNOWN)[0]
    (stay, created) = Stay.objects.get_or_create(
        room=room, start=params.start(url), end=params.end(url),
        price_per_night=Money(price_per_night, 'USD'))
    if not stay.looked_up_on:
      stay.looked_up_on = date.today()
    stay.last_seen_on = date.today()
    stay.save()


class UrlExpert(object):
  def page(self, url):
    match = re.compile(r'section_offset=(\d+)').search(url)
    if not match:
      return 0
    return int(match.groups()[0])

  def price_min(self, url):
    return self._get_int('price_min', url) or price_min()

  def price_max(self, url):
    return self._get_int('price_max', url)

  def start(self, url):
    return self._get_date('checkin', url)

  def end(self, url):
    return self._get_date('checkout', url)

  def city(self, url):
    found_city = re.compile(r'/s/([A-Za-z]+)').search(url)
    if not found_city:
      return
    return found_city.groups()[0]

  def set_page_url(self, url, page):
    return self._set_query_string_attr(url, 'section_offset', page)

  def set_price_url(self, url, lower_bound, upper_bound):
    url = self._set_query_string_attr(url, 'price_min', lower_bound)
    return self._set_query_string_attr(url, 'price_max', upper_bound)

  def set_weekend_url(self, url, start, end):
    # checkin=2018-04-06&checkout=2018-04-08
    url = self._set_query_string_attr(url, 'checkin', self._format_date(start))
    return self._set_query_string_attr(url, 'checkout', self._format_date(end))

  def validate(self, url):
    valid = True
    if not self.city(url):
      print('You need to set a city for this to work.')
      valid = False
    if not self.start(url) or not self.end(url):
      print('You need to set a checkin and checkout for this to work.')
      valid = False
    if not self.price_min(url) and not self.price_max(url):
      print('You need to set a price range for this to work.')
      valid = False
    return valid

  def next_url(self, ff):
    """
    for each city
      for each weekend
        for each price
          for each page
            for each home

    This really has to be done with a scraper, and scrapers break. Make it easy
    to examine the current break through an interactive browser and an
    interactive shell, make it easy to overwrite the logic, make it easy to
    pick up where I left off. Make it easy to babysit the scraper.

    OK so where we are in this massive loop is all stored in the query
    string. From a query string we should be able to compute where to
    go next.
    """
    next_page = self.next_page_url(ff)
    if next_page:
      return next_page

    url = self.first_page_url(ff.current_url())

    next_price = self.next_price_url(url)
    if next_price:
      return next_price

    url = self.first_price_url(url)

    next_weekend = self.next_weekend_url(url)
    if next_weekend:
      return next_weekend

    url = self.first_weekend_url(url)

    next_city = self.next_city_url(url)
    if next_city:
      url = self.first_page_url(next_city)
      url = self.first_price_url(url)
      return self.first_weekend_url(url)

  def first_page_url(self, url):
    return self.set_page_url(url, 0)

  def first_price_url(self, url):
    return self.set_price_url(
        url, price_min(), price_min() + self._price_step(price_min()))

  def first_weekend_url(self, url):
    span = weekends()[0]
    return self.set_weekend_url(url, span[0], span[1])

  def next_page_url(self, ff):
    url = ff.current_url()

    more_pages = self.page(url) < max_page(ff)
    if more_pages:
      return self.set_page_url(url, self.page(url) + 1)

  def next_price_url(self, url):
    price_min = self.price_min(url)
    step = self._price_step(price_min)
    price_min += step
    if price_min <= largest_price():
      price_max = price_min + self._price_step(price_min)
      if price_max > largest_price():
        price_max = None
      return self.set_price_url(url, price_min, price_max)

  def next_weekend_url(self, url):
    start = self.start(url)
    end = self.end(url)
    current_time_span = (start, end)
    use_the_next_one = False
    for time_span in weekends():
      if use_the_next_one:
        return self.set_weekend_url(url, time_span[0], time_span[1])
      use_the_next_one = current_time_span == time_span

  def next_city_url(self, url):
    use_the_next_one = False
    on_city = self.city(url)
    for city_template_url in cities():
      if use_the_next_one:
        return city_template_url
      use_the_next_one = on_city == self.city(city_template_url)

  def _price_step(self, price_min):
    if price_min < 200:
      return 20
    return int(price_min / 10)

  def _get_int(self, key, url):
    found_str = self._get_value(key, url)
    if found_str:
      return int(found_str)

  def _get_date(self, key, url):
    found_str = self._get_value(key, url)
    if found_str:
      return parse_date(found_str)

  def _get_value(self, key, url):
    found = re.compile(r'{}=([^&]+)'.format(key)).search(url)
    if found:
      return found.groups()[0]

  def _format_date(self, d):
    return d.strftime('%Y-%m-%d')

  def _set_query_string_attr(self, url, key, value=None):
    key_finder = re.compile(r'{}=[^&]+'.format(key))
    if key_finder.search(url):
      if value:
        return key_finder.sub('{}={}'.format(key, value), url)
      return key_finder.sub('', url)
    elif value:
      return url + '&{}={}'.format(key, value)
    return url

def max_page(ff):
  page_links = ff.find_elements_by_xpath(
      '//a[contains(@href,\'section_offset\')]')
  if page_links:
    page_link = page_links[-1]
    return int(UrlExpert().page(page_link.get_attribute('href')))
  return 0

def cities():
  return [
      'https://www.airbnb.com/s/Boston--MA--United-States/homes?refinement_paths%5B%5D=%2Fhomes&query=Boston%2C%20MA%2C%20United%20States&place_id=ChIJGzE9DS1l44kRoOhiASS_fHg&allow_override%5B%5D=&checkin=2018-04-06&checkout=2018-04-08&price_min=27&price_max=132&s_tag=de5eMUJy',
      'https://www.airbnb.com/s/Philadelphia--PA--United-States/homes?refinement_paths%5B%5D=%2Fhomes&query=Philadelphia%2C%20PA%2C%20United%20States&place_id=ChIJ60u11Ni3xokRwVg-jNgU9Yk&allow_override%5B%5D=&checkin=2018-04-06&checkout=2018-04-08&price_min=27&price_max=132&s_tag=2Wc_mNFR',
      'https://www.airbnb.com/s/Dallas--TX--United-States/homes?refinement_paths%5B%5D=%2Fhomes&query=Dallas%2C%20TX%2C%20United%20States&place_id=ChIJS5dFe_cZTIYRj2dH9qSb7Lk&allow_override%5B%5D=&checkin=2018-04-06&checkout=2018-04-08&price_min=27&price_max=132&s_tag=4xyCyJPL',
      'https://www.airbnb.com/s/Nashville--TN--United-States/homes?refinement_paths%5B%5D=%2Fhomes&query=Nashville%2C%20TN%2C%20United%20States&place_id=ChIJPZDrEzLsZIgRoNrpodC5P30&allow_override%5B%5D=&checkin=2018-04-06&checkout=2018-04-08&price_min=27&price_max=132&s_tag=aoUnd2TH',
      'https://www.airbnb.com/s/Hoboken--NJ--United-States/homes?refinement_paths%5B%5D=%2Fhomes&query=Hoboken%2C%20NJ%2C%20United%20States&place_id=ChIJ0TMVjWBXwokRh783EWrKtkQ&allow_override%5B%5D=&checkin=2018-04-06&checkout=2018-04-08&price_min=27&price_max=132&s_tag=dpDD272t',
      'https://www.airbnb.com/s/Austin--TX--United-States/homes?refinement_paths%5B%5D=%2Fhomes&query=Austin%2C%20TX%2C%20United%20States&allow_override%5B%5D=&checkin=2018-04-06&checkout=2018-04-08&ib=true&price_min=908&ne_lat=30.358006209196258&ne_lng=-97.62201517502535&sw_lat=30.18072743215689&sw_lng=-97.95091837326754&search_by_map=true&zoom=11&s_tag=LGbXmWtF',
      'https://www.airbnb.com/s/Washington--DC--United-States/homes?refinement_paths%5B%5D=%2Fhomes&query=Washington%2C%20DC%2C%20United%20States&place_id=ChIJW-T2Wt7Gt4kRKl2I1CJFUsI&allow_override%5B%5D=&checkin=2018-04-06&checkout=2018-04-08&price_min=27&price_max=132&s_tag=VoVw7cfk']

def weekends():
  friday = 5
  day_of_week = int(date.today().strftime('%w'))
  if day_of_week > friday:
    day_of_week -= 7
  days_until_friday = friday - day_of_week
  next_friday = date.today() + timedelta(days=days_until_friday)
  return_me = []
  while (next_friday - date.today()).days < 14:
    return_me.append((next_friday, next_friday + timedelta(days=2)))
    next_friday += timedelta(days=7)
  return return_me

def price_min():
  return 10

def largest_price():
  return 900








def check_all_avail(ff):
  if not ff.is_started():
    ff.restart()
  if ff.get_window_size()['width'] > 1100:
    ff.set_window_size(768, 848)

  since_last_restart = 0
  rooms = Room.objects.filter(availability=UNKNOWN)
  how_many_left = rooms.count()
  hours_left = how_many_left / 360
  print('{} rooms left to check, which\'ll take about {} hours.'.format(
      how_many_left, hours_left))
  for room in rooms:
    if since_last_restart >= RESTART_FF_EVERY_N_REQUESTS:
      ff.restart()
      since_last_restart = 0
    if not navigate_to_room(ff, room.airbnb_id):
      print('Room doesn\'t exist anymore. Deleting.')
      room.delete()
      continue
    room.availability = check_availability(ff)
    room.save()
    since_last_restart += 1

def check_availability(ff):
  open_booking(ff)
  days_to_check = list(check_availability_days())
  total_days = len(days_to_check)
  available_days = 0
  for day in days_to_check:
    if available(ff, day):
      available_days += 1
  if available_days == total_days:
    to_return = ALL_AVAILABILITY
  elif available_days == 0:
    to_return = NO_AVAILABILITY
  else:
    to_return = SOME_AVAILABILITY
  print(to_return)
  return to_return

def navigate_to_room(ff, airbnb_room_id):
  url = 'https://www.airbnb.com/rooms/{}'.format(airbnb_room_id)
  ff.get(url)
  return url == ff.current_url()

def open_booking(ff):
  try:
    # One time, somebody put "Book with confidence!" in their description.
    book = ff.find_exact_text('Request to Book', 'span')
    book = book or ff.find_exact_text('Book', 'span')
    book.find_element_by_xpath(
        'ancestor::button').click()
  except ElementClickInterceptedException:
    pass  # It's already open.
  # This part is tricky. I'm not sure how exactly Airbnb opens the
  # calendar, but it's difficult to trigger without a human powered
  # mouse! But I got to work by clicking on checkin, switching to a second
  # tab, and then switching back. But then the code to open that second tab
  # stopped working. So now I pop open a new window then close it.
  # Something about refocussing on the window
  # after you've clicked on the element will open it.
  # I wonder if the best answer might be to actually-actually move the
  # mouse. I'm looking at Python-uinput or PyMouse for example.
  ActionChains(ff._webdriver).move_to_element(
      ff.find_element_by_id('checkin')).click().perform()
  time.sleep(1)
  if not ff.find_text('Su', 'small'):
    ff.blur_then_focus()
  # Su, Mo, Tu, We, ...
  if not ff.find_text('Su', 'small'):
    print('You gotta focus on the Firefox window for this to work.')
  while not ff.find_text('Su', 'small'):
    time.sleep(1)

def check_availability_days():
  on = date.today() + timedelta(days=1)
  end = on + timedelta(days=31)
  while on < end:
    yield on
    on += timedelta(days=1)

def available(ff, day):
  day_str = day.strftime('%B %-d')
  day_xpath = '//*[contains(@aria-label,\'{}\')]'.format(day_str)
  day_elt = ff.find_element_by_xpath(day_xpath)
  aria_label = day_elt.get_attribute('aria-label')
  yes = aria_label.find('It\'s available') >= 0
  no = aria_label.find('Not available') >= 0
  if not yes and not no:
    print('Neither available nor unavailable? Here\'s what it had: {}'.format(
        aria_label))
  return yes
