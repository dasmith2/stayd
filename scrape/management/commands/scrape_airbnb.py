import logging
import os

from django.core.management.base import BaseCommand

from scrape.airbnb_scraper import (
    AirbnbScraper, get_browser, profile_path_name,
    AIRBNB_IS_DOWN, OK, ERROR, LOGIN_REQUIRED)
from scrape.utils import api_get
from scrape.airvatar import WebUserManager
from scrape.browser import Browser

ACTION = 'action'
LISTINGS = 'listings'
RESERVATIONS = 'reservations'


class Command(BaseCommand):
  help = 'Scrape listings, reservations, and payouts off Airbnb.'

  def add_arguments(self, parser):
    action = parser.add_argument(
        ACTION, choices=[LISTINGS, RESERVATIONS], help=(
            'Specifying reservations pulls down Paypal payouts and '
            'paid out reservations.'))
    parser.add_argument('--airvatar', help=(
        'The name of a single airvatar. If none is specified, it runs for '
        'all airvatars.'))

  def handle(self, *args, **options):
    """ If we get an unexpected ERROR or a good ol' fashioned crash, the
    browser should stay up and progress should halt so we can figure out what
    the heck happened and fix it. If AIRBNB_IS_DOWN, halt progress but also
    close the browser. If we're OK, keep going, unless we're done, in which
    case close the browser. """
    scraper = AirbnbScraper()
    got = OK
    if options['airvatar']:
      json_airvatars = [airvatar_manager.get_airvatar(options['airvatar'])]
    else:
      airvatars = airvatar_manager.get_airvatars()
    for airvatar in airvatars:
      if got == OK:
        browser = Browser(airvatar)
        browser.start()
        action = options['action']
        if action == LISTINGS:
          got = scraper.save_listings(browser)
        elif action == RESERVATIONS:
          got = scraper.save_payouts_and_reservations(browser)
        if got in (OK, AIRBNB_IS_DOWN):
          browser.close()