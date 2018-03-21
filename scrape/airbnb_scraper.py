from datetime import datetime
import logging
import re
import time

from django.conf import settings
from django.urls import reverse
import requests
from requests.auth import HTTPBasicAuth
from selenium.common.exceptions import WebDriverException

from guests.models import Guest
from listings.models import Listing
from listings.serializers import ListingSerializer
from pays.models import PaypalPayin
from pays.serializers import PaypalPayinSerializer
from rentals.models import Rental
from reservations.models import Reservation, ReservationLineItem
from reservations.serializers import ReservationSerializer
from scrape.browser import Browser
from util.channels import AIRBNB


TRANSACTIONS_URL = 'https://www.airbnb.com/users/transaction_history'
RESERVATIONS_URL = 'https://www.airbnb.com/my_reservations?all=1'
RESERVATION_URL = 'https://www.airbnb.com/reservation/itinerary?code={}'
LISTINGS_URL = 'https://www.airbnb.com/hosting/listings'
LISTING_URL = 'https://www.airbnb.com/manage-your-space/{}/details'
RESOLUTIONS_URL = 'https://www.airbnb.com/resolutions'
RESOLUTION_URL = 'https://www.airbnb.com/resolutions/{}'  # e.g. 5703871
USER_URL = 'https://www.airbnb.com/users/show/{}'  # e.g. 104229091

AIRBNB_IS_DOWN = 'AIRBNB_IS_DOWN'
OK = 'OK'
ERROR = 'ERROR'


class AirbnbScraper(object):
  def __init__(self, browser):
    self.browser = browser

  def save_listings(self):
    got = self._get(LISTINGS_URL)
    if not got == OK:
      return got
    id_finder = re.compile(r'manage-your-space/(\d+)')
    links = self.browser.find_elements_by_xpath(
        '//a[contains(@href,\'manage-your-space\')]')
    hrefs = (link.get_attribute('href') for link in links)
    ids = set(id_finder.search(href).groups()[0] for href in hrefs)
    for channel_listing_id in ids:
      got = self._get(LISTING_URL.format(channel_listing_id))
      if got != OK:
        return got
      got = self._save_listing(
          self._extract_listing(channel_listing_id))
      if not got == OK:
        return got
    return OK

  def save_payouts_and_reservations(self):
    # https://www.airbnb.com/reservation/itinerary?code=HM3YRMQBDC
    got = self._get(TRANSACTIONS_URL)
    if not got == OK:
      return got
    table = self.browser.find_element_by_class_name('transaction-table')
    tbody = table.find_element_by_tag_name('tbody')
    rows = tbody.find_elements_by_tag_name('tr')
    # We'll circle back around to these once we get all the payouts off the
    # page.
    channel_reservation_ids = []
    for index, row in enumerate(rows):
      cells = row.find_elements_by_tag_name('td')
      type_text = cells[1].text
      if type_text == 'Payout':
        self._save_payout(self._extract_payout(cells))
      elif type_text == 'Reservation':
        channel_reservation_ids.append(
            self._extract_channel_reservation_id(cells))
      elif type_text == 'Resolution Adjustment':
        self._save_resolution_adjustment(
            self._extract_resolution_adjustment(cells))
      else:
        logging.error((
            'I expected cells[1] of row {} to contain Payout, Reservation, '
            'or Resolution Adjustment, but it contained {} instead.').format(
                index, type_text))
        return ERROR
    for channel_reservation_id in channel_reservation_ids:
      got = self._get(RESERVATION_URL.format(channel_reservation_id))
      if got != OK:
        return got
      got = self._save_reservation(self._extract_reservation(
          channel_reservation_id, is_paid_in=True))
      if got != OK:
        return got
    return OK

  def _get(self, url):
    times = 0
    max_times = 3
    while times < max_times:
      try:
        self.browser.get(url)
        passwords = self.browser.find_elements_by_id('signin_password')
        if passwords:
          passwords[0].send_keys('ExecRes2017!!!!')
          self.browser.find_element_by_id('user-login-btn').click()
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
              'Loading {} failed {} times with {}. You\'ll have to '
              'try again later.').format(url, max_times, err))
        # This is a failure to establish a secure connection and it happens
        # instantly. In that case, wait a second rather than just failing 3
        # times in a row really fast.
        if str(err).find('e=nssFailure2'):
          time.sleep(1)
    return AIRBNB_IS_DOWN

  def _save_dict(self, api_name, data_dict):
    got = requests.post(
        settings.STAYD_API_BASE_URL + reverse(api_name),
        json=data_dict,
        auth=HTTPBasicAuth(
            settings.STAYD_API_USER, settings.STAYD_API_PASSWORD))
    if got.ok:
      return OK
    logging.error(
        'Couldn\'t save to {}. Got status {}:{} because {}'.format(
            api_name, got.status_code, got.reason, got.content))
    return ERROR

  def _save_payout(self, payout):
    return self._save_dict(
        'paypal-payins-api', PaypalPayinSerializer(payout).data)

  def _save_resolution_adjustment(self, resolution_adjustment):
    """
    return self._save_dict(
        'resolution-adjustments-api',
        ResolutionAdjustmentSerializer(resolution_adjustment).data)
    """

  def _save_reservation(self, reservation):
    return self._save_dict(
        'reservations-api', ReservationSerializer(reservation).data)

  def _save_listing(self, listing):
    return self._save_dict(
        'listings-api', ListingSerializer(listing).data)

  def _extract_reservation(
      self, channel_reservation_id, is_paid_in=False):
    res = Reservation(
        channel_reservation_id=channel_reservation_id, is_paid_in=is_paid_in)
    # We replace the line_items() function with a property here so we can
    # manually add line items that will get serialized and sent to the server.
    res.line_items = []
    res.guest = Guest()
    guest_panel = self.browser.find_element_by_class_name('guest-info-panel')
    name_elt = guest_panel.find_element_by_tag_name('strong')
    res.guest.full_name = name_elt.text
    # 'Joined in March 2018\nChengdu, China'
    joined_and_from = name_elt.find_element_by_xpath('../div').text
    (joined, res.guest.airbnb_says_theyre_from) = joined_and_from.split('\n')
    res.guest.joined_airbnb_when = datetime.strptime(
        joined, 'Joined in %B %Y').date()
    message_guest_span = self.browser.find_element_by_xpath(
        '//span[contains(text(),\'Message guest\')]')
    phones = message_guest_span.find_elements_by_xpath('../../div/div')
    # TODO denormalize phones because I didn't see it coming that people
    # might have more than one phone haha
    res.guest.phone = ', '.join(phone.text for phone in phones)
    # If an element is invisible, the .text attribute is an empty string.
    # Airbnb swaps out two layouts depending on the size of the browser.
    # So we should check them both, otherwise the scraper will fail if the
    # browser window is resized for any reason.
    check_in_out = self.browser.find_element_by_class_name('checkin-checkout')
    check_in_out_cols1 = check_in_out.find_elements_by_class_name('col-3')
    check_in_out_cols2 = check_in_out.find_elements_by_class_name('col-sm-6')
    res.check_in = self._parse_checkin(
        check_in_out_cols1[1].text or check_in_out_cols2[0].text)
    res.check_out = self._parse_checkout(
        check_in_out_cols1[3].text or check_in_out_cols2[1].text)
    listing_row = self.browser.find_elements_by_class_name(
        'itinerary-card')[1].find_elements_by_class_name('panel-body')[1]
    list_url = listing_row.find_element_by_tag_name('a').get_attribute('href')
    res.channel_listing_id = re.compile(
        r'rooms/(\w+)').search(list_url).groups()[0]
    payout_table = self.browser.find_element_by_class_name('payout-table')
    for row in payout_table.find_elements_by_tag_name('tr'):
      cells = row.find_elements_by_tag_name('td')
      what_for = cells[0].text
      how_much = self._parse_amount(cells[1].text)
      if what_for == 'Total Payout':
        res.total_payin = how_much
      else:
        # '$125.00 x 2 nights'
        found_rent = re.compile(r'\$(\d+\.\d+) x (\d+) night').match(what_for)
        if found_rent:
          res.price_per_night = float(found_rent.groups()[0])
          res.night_count = int(found_rent.groups()[1])
          what_for = 'Rent'
        res.line_items.append(
            ReservationLineItem(name=what_for, value=how_much))
    return res

  def _extract_listing(self, channel_listing_id):
    listing = Listing(
        channel=AIRBNB,
        channel_listing_id=channel_listing_id,
        firefox_profile=self.browser.airvatar.name,
        rental=Rental())

    def _parent(title_text):
      xpath = '//*[contains(text(),\'{}\')]'.format(title_text)
      header = self.browser.find_element_by_xpath(xpath)
      parent = header.find_element_by_xpath('../../../..')
      return parent

    listing.rental.airbnb_address_scrape = _parent(
        'Location').find_elements_by_xpath(
        'div/div/div')[1].text
    listing.title = _parent('Title & description').find_elements_by_xpath(
        'div/div')[2].text
    room = _parent('Rooms & guests')

    def _room_value(name):
      xpath = '//span[contains(text(),\'{}:\')]/../span[2]'.format(name)
      return room.find_element_by_xpath(xpath).text.strip()

    listing.rental.accommodates = _room_value('Accommodates')
    listing.rental.bathrooms = _room_value('Bathrooms')
    listing.rental.bedrooms = _room_value('Bedrooms')
    listing.rental.property_type = _room_value('Property type')
    listing.rental.room_type = _room_value('Room type')
    return listing

  def _parse_amount(self, dollar_amount_str):
    negative_match = re.compile(r'\(\$([\d\.]+)\)').match(dollar_amount_str)
    if negative_match:
      return -1 * float(negative_match.groups()[0])
    return float(dollar_amount_str.replace('$', ''))

  def _parse_checkin(self, check_in_str):
    # check_in_str should be like 'Sat, Mar 03\nAfter 3PM'
    # 'Sat, Mar 03\nAfter 03PM' Note the zero padded time
    check_in_str = re.sub(
        r'\nAfter (\d)(\w)M', r'\nAfter 0\1\2M', check_in_str)
    check_in_str = check_in_str.replace('Check In\n', '')
    # We're shooting for something like 'Sat, Mar 032018 03PM'
    after = re.compile(r'\nAfter')
    # It could be January, and there's a reservation from December, well
    # that would be last year. We don't have to worry about next year
    # because reservations only show up on this list after they were paid
    # for which is after checkin, so checkin is now or in the past.
    format = '%a, %b %d%Y %I%p'
    check_in_str_last_year = after.sub(str(datetime.now().year), check_in_str)
    check_in_last_year = datetime.strptime(check_in_str_last_year, format)
    check_in_str_this_year = after.sub(str(datetime.now().year), check_in_str)
    check_in_this_year = datetime.strptime(check_in_str_this_year, format)
    if (datetime.now() - check_in_this_year).days >= -1:
      return check_in_this_year
    return check_in_last_year

  def _parse_checkout(self, check_out_str):
    # check_out_str should be like 'Mon, Mar 05\n1PM'
    # 'Mon, Mar 05\n01PM'
    check_out_str = re.sub(r'\n(\d)(\w)M', r'\n0\1\2M', check_out_str)
    check_out_str = check_out_str.replace('Check Out\n', '')
    # 'Mon, Mar 05\n01PM2018'
    check_out_str += str(datetime.now().year)
    return datetime.strptime(check_out_str, '%a, %b %d\n%I%p%Y')

  def _extract_channel_reservation_id(self, cells):
    return cells[2].find_element_by_tag_name('a').text

  def _extract_payout(self, cells):
    pay = PaypalPayin()
    pay.when = datetime.strptime(cells[0].text, '%m/%d/%Y')
    payment_routing_pattern = r'Transfer to ([^\s]+) \((\w+)\)\n(\w+)'
    payment_routing_parser = re.compile(payment_routing_pattern)
    payment_routing = cells[2].text
    routing_matches = payment_routing_parser.match(cells[2].text)
    if not routing_matches:
      raise Exception((
          'I expected to parse an email, currency, and id out of "{}", with '
          'the regular expression "{}", but I was unable '
          'to.').format(payment_routing, payment_routing_pattern))
    groups = routing_matches.groups()
    pay.to_email, pay.currency, pay.transaction_id = groups
    pay.amount = float(
        re.compile(r'([\d\., ]+)').search(cells[4].text).groups()[0])
    return pay

  def _extract_resolution_adjustment(self, cells):
    pass

  def login(self):
    got = self._get(TRANSACTIONS_URL)
    if not got == OK:
      return got
    passwords = self.browser.find_elements_by_id('signin_password')
    if passwords:
      emails = self.browser.find_elements_by_id('signin_email')
      if emails:
        self._sign_in_with_username(emails[0], passwords[0])
      else:
        self._confirm_with_password_only(passwords[0])

  def _confirm_with_password_only(self, password_elt):
    password_elt.send_keys(self.browser.airvatar.airbnb_password)
    self.browser.find_element_by_id('user-login-btn').click()

  def _sign_in_with_username(self, email_elt, password_elt):
    email_elt.send_keys(self.browser.airvatar.gmail_address)
    # The browser may store a password and auto fill it in.
    password_elt.clear()
    password_elt.send_keys(self.browser.airvatar.airbnb_password)
    remember_me = self.browser.find_element_by_id('remember_me2')
    if not remember_me.is_selected():
      remember_me.click()
    self.browser.find_element_by_id('user-login-btn').click()
    is_it_really_you = self.browser.find_elements_by_xpath(
        '//div[contains(text(),\'Help us confirm it’s really you\')]')
    if len(is_it_really_you):
      self.browser.find_element_by_xpath(
          '//div[contains(text(),\'Get an email\')]').click()
      self.browser.find_element_by_xpath(
          '//span[contains(text(),\'Send code\')]').click()

      security_code = self._get_security_code()

      for i in range(4):
        self.browser.find_element_by_id(
            'codeinput_{}'.format(i)).send_keys(security_code[i])
    if len(self.browser.find_elements_by_id('user-login-btn')):
      print('Username {} and password {} aren\'t working for {}!'.format(
          self.browser.airvatar.gmail_address,
          self.browser.airvatar.airbnb_password,
          self.browser.airvatar.name))

  def _get_security_code(self):
    browser2 = Browser(self.browser.airvatar)
    browser2.start()

    browser2.get('https://mail.google.com/')
    sign_in = browser2.find_elements_by_xpath(
        '//a[contains(text(),\'Sign In\')]')
    if len(sign_in):
      sign_in[0].click()
      browser2.find_element_by_id('identifierId').send_keys(
          browser2.airvatar.gmail_address)
      browser2.find_element_by_xpath(
          '//span[contains(text(),\'Next\')]').click()
      browser2.find_element_by_name('password').send_keys(
          browser2.airvatar.gmail_password)
      browser2.find_element_by_xpath(
          '//span[contains(text(),\'Next\')]').click()

    print(
        'As soon as I see an email with \'Your security code is\' I\'ll be '
        'able to finish signing into Airbnb.')

    # We'll have to wait for this.
    def try_get_security_code():
      code_boxes = browser2.find_elements_by_xpath(
          '//*[contains(text(),\'Your security code is\')]')
      if len(code_boxes):
        content = code_boxes[0].get_attribute('innerHTML')
        return re.compile(
            r'Your security code is (\d+)').search(content).groups()[0]
    security_code = try_get_security_code()
    while not security_code:
      time.sleep(5)
      security_code = try_get_security_code()
    browser2.close()
    return security_code
