from datetime import datetime
import logging
import re
import time

from django.conf import settings
from django.urls import reverse
import requests
from requests.auth import HTTPBasicAuth
from selenium.common.exceptions import ElementNotInteractableException

from guests.models import Guest
from listings.models import Listing
from listings.serializers import ListingSerializer
from pays.models import PaypalPayin
from pays.serializers import PaypalPayinSerializer
from rentals.models import Rental
from reservations.models import Reservation, ReservationLineItem
from reservations.serializers import ReservationSerializer
from scrape.browser import Browser, OK, ERROR
from util.channels import AIRBNB


TRANSACTIONS_URL = 'https://www.airbnb.com/users/transaction_history'
RESERVATIONS_URL = 'https://www.airbnb.com/my_reservations?all=1'
RESERVATION_URL = 'https://www.airbnb.com/reservation/itinerary?code={}'
LISTINGS_URL = 'https://www.airbnb.com/hosting/listings'
LISTING_URL = 'https://www.airbnb.com/manage-your-space/{}/details'
RESOLUTIONS_URL = 'https://www.airbnb.com/resolutions'
RESOLUTION_URL = 'https://www.airbnb.com/resolutions/{}'  # e.g. 5703871
USER_URL = 'https://www.airbnb.com/users/show/{}'  # e.g. 104229091


"""
TODOs
- Handle reservation adjustments, misc credits
- Handle direct bank account deposit payins
- Be smart about what we scrape. No need to always scrape everything.
"""


class AirbnbScraper(object):
  def __init__(self, browser):
    self.browser = browser

  def save_listings(self):
    # This page says 'Your Listings' if you've got more than one, but this
    # still matches. I comment to avoid confusion. This pulls a list
    # of all listings, not just a single listing.
    got = self.browser.get_until_text(LISTINGS_URL, 'Your Listing')
    if not got == OK:
      return got
    for channel_listing_id in self.browser.find_href_ids('manage-your-space/'):
      got = self.browser.get(LISTING_URL.format(channel_listing_id))
      if self.browser.find_text('Great progress', 'span'):
        # This particular listing isn't ready to go yet so we can skip it.
        continue
      if got != OK:
        return got
      got = self._save_listing(
          self._extract_listing(channel_listing_id))
      if not got == OK:
        return got
    return OK

  def save_payouts_and_reservations(self):
    # https://www.airbnb.com/reservation/itinerary?code=HM3YRMQBDC
    got = self.browser.get_until_class_name(
        TRANSACTIONS_URL, 'transaction-table')
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
        payout = self._extract_payout(cells)
        # There may be no payout if it's a direct bank transfer, say.
        if payout:
          self._save_payout(payout)
      elif type_text == 'Reservation':
        channel_reservation_ids.append(
            self._extract_channel_reservation_id(cells))
      elif type_text in ('Resolution Adjustment', 'Misc Credit'):
        # Here's an example misc credit row:
        # 07/07/2016  Misc Credit  <no Details>   $140.00 <no Paid Out>
        self._save_resolution_adjustment(
            self._extract_resolution_adjustment(cells))
      else:
        logging.error((
            'I expected cells[1] of row {} to contain Payout, Reservation, '
            'or Resolution Adjustment, but it contained {} instead.').format(
                index, type_text))
        return ERROR
    for channel_reservation_id in channel_reservation_ids:
      url = RESERVATION_URL.format(channel_reservation_id)
      got = self.browser.get(url)
      if got != OK:
        return got
      # If a reservation never actually happened, Airbnb will just jump
      # you to some random url like airbnb.com/hosting/ or something.
      # There would be a corresponding adjustment in that case.
      if self.browser.current_url() == url:
        got = self._save_reservation(self._extract_reservation(
            channel_reservation_id, is_paid_in=True))
        if got != OK:
          return got
    return OK

  def _save_dict(self, api_name, data_dict):
    got = requests.post(
        settings.STAYD_API_BASE_URL + reverse(api_name),
        json=data_dict,
        auth=HTTPBasicAuth(
            settings.STAYD_API_USER, settings.STAYD_API_PASSWORD))
    if got.ok:
      return OK
    logging.error(
        'Couldn\'t save {} to {}. Got status {}:{} because {}'.format(
            data_dict, api_name, got.status_code, got.reason,
            got.content[:500]))
    return ERROR

  def _save_payout(self, payout):
    return self._save_dict(
        'create-paypal-payins-api', PaypalPayinSerializer(payout).data)

  def _save_resolution_adjustment(self, resolution_adjustment):
    # TODO(Dave)
    pass

  def _save_reservation(self, reservation):
    return self._save_dict(
        'create-reservations-api', ReservationSerializer(reservation).data)

  def _save_listing(self, listing):
    return self._save_dict(
        'create-listings-api', ListingSerializer(listing).data)

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
    rental = Rental(time_zone=None, currency=None)
    listing = Listing(
        channel=AIRBNB,
        channel_listing_id=channel_listing_id,
        rental=rental)
    listing.airvatar_name = self.browser.airvatar.name

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
    rooms = _room_value('Bedrooms')
    if rooms == 'Studio':
      rooms = 0
    listing.rental.bedrooms = rooms
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
    # or 'Tue, Jul 05\n3PM - 8PM'. This turns the second into
    # the first.
    check_in_str = re.sub(
        r'\n(\d+)(\w)M - \d+\wM', r'\nAfter \1\2M', check_in_str)
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
    check_in_str_last_year = after.sub(
        str(datetime.now().year - 1), check_in_str)
    check_in_last_year = datetime.strptime(check_in_str_last_year, format)
    check_in_str_this_year = after.sub(str(datetime.now().year), check_in_str)
    check_in_this_year = datetime.strptime(check_in_str_this_year, format)
    if (datetime.now() - check_in_this_year).days >= -1:
      return check_in_this_year
    return check_in_last_year

  def _parse_checkout(self, check_out_str):
    # check_out_str should be like 'Mon, Mar 05\n1PM'
    # or 'Thu, Jul 07\n12PM (noon)
    check_out_str = check_out_str.replace(' (noon)', '')
    # 'Mon, Mar 05\n01PM'
    check_out_str = re.sub(r'\n(\d)(\w)M', r'\n0\1\2M', check_out_str)
    check_out_str = check_out_str.replace('Check Out\n', '')
    # 'Mon, Mar 05\n01PM2018'
    check_out_str += str(datetime.now().year)
    return datetime.strptime(check_out_str, '%a, %b %d\n%I%p%Y')

  def _extract_channel_reservation_id(self, cells):
    return cells[2].find_element_by_tag_name('a').text

  def _extract_payout(self, cells):
    is_direct_bank_transfer = re.compile(
        r'Transfer to \*+\d+').match(cells[2].text)
    if is_direct_bank_transfer:
      return None
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
    # TODO(Dave)
    pass

  def login(self):
    got = self.browser.get(TRANSACTIONS_URL)
    if not got == OK:
      return got
    while self._is_login_screen():
      if self._signin_password_elt():
        self._sign_in_with_password()
      elif self._is_it_really_you():
        self._confirm_its_really_me()
      elif self._they_dont_recognize_device():
        self._make_them_recognize_device()
    return OK

  def _they_dont_recognize_device(self):
    return self.browser.find_text('We don’t recognize this device', 'div')

  def _is_it_really_you(self):
    return self.browser.find_text('Help us confirm it’s really you', 'div')

  def _signin_password_elt(self):
    return self.browser.find_elements_by_id('signin_password')

  def _is_login_screen(self):
    return any([
        self._they_dont_recognize_device(),
        self._is_it_really_you(),
        self._signin_password_elt()])

  def _sign_in_with_password(self):
    passwords = self._signin_password_elt()
    emails = self.browser.find_elements_by_id('signin_email')
    if emails:
      self._sign_in_with_username(emails[0], passwords[0])
    else:
      self._confirm_with_password_only(passwords[0])

  def _sign_in_with_username(self, email_elt, password_elt):
    email_elt.send_keys(self.browser.airvatar.gmail_address)
    # The browser may store a password and auto fill it in.
    password_elt.clear()
    password_elt.send_keys(self.browser.airvatar.airbnb_password)
    remember_me = self.browser.find_element_by_id('remember_me2')
    if not remember_me.is_selected():
      remember_me.click()
    self.browser.find_element_by_id('user-login-btn').click()

  def _confirm_with_password_only(self, password_elt):
    password_elt.send_keys(self.browser.airvatar.airbnb_password)
    self.browser.find_element_by_id('user-login-btn').click()

  def _confirm_its_really_me(self):
    self.browser.find_text('Get an email', 'div').click()
    self.browser.find_text('Send code', 'div').click()
    self._enter_security_code()

  def _make_them_recognize_device(self):
    self.browser.find_text('email', 'div').click()
    self.browser.find_text('Next', 'span').click()
    self._enter_security_code()

  def _enter_security_code(self):
    security_code = self._get_security_code()

    for i in range(4):
      self.browser.find_element_by_id(
          'codeinput_{}'.format(i)).send_keys(security_code[i])

  def _get_security_code(self, browser2=None):
    if not browser2:
      browser2 = Browser(self.browser.airvatar)
    browser2.start()

    browser2.get('https://mail.google.com/')
    sign_in = browser2.find_text('Sign In', 'a')
    if sign_in:
      sign_in.click()
      browser2.send_keys(
          browser2.find_element_by_id('identifierId'),
          browser2.airvatar.gmail_address)
      browser2.click(browser2.find_text('Next', 'span'))
      browser2.send_keys(
          browser2.find_element_by_name('password'),
          browser2.airvatar.gmail_password)
      browser2.click(browser2.find_text('Next', 'span'))

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
