import logging
import os

from django.core.management.base import BaseCommand

from scrape.airbnb_scraper import (
    AirbnbScraper, get_browser, profile_path_name,
    AIRBNB_IS_DOWN, OK, ERROR, LOGIN_REQUIRED)

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
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--profile', help=(
        'The path to a single Firefox profile.'))
    group.add_argument('--profiles', help=(
        'The path to a folder containing Firefox profiles.'))

  def handle(self, *args, **options):
    """ If we get an unexpected ERROR or a good ol' fashioned crash, the
    browser should stay up and progress should halt so we can figure out what
    the heck happened and fix it. If AIRBNB_IS_DOWN, halt progress but also
    close the browser. If we're OK, keep going, unless we're done, in which
    case close the browser. """
    scraper = AirbnbScraper()
    got = OK
    if options['profile']:
      profile_paths = [options['profile']]
    elif options['profiles']:
      profile_paths = os.listdir(options['profiles'])
    for profile_path in profile_paths:
      if got in (OK, LOGIN_REQUIRED):
        browser = get_browser(profile_path)
        action = options['action']
        if action == LISTINGS:
          got = scraper.save_listings(browser, profile_path)
        elif action == RESERVATIONS:
          got = scraper.save_payouts_and_reservations(browser)
        if got == LOGIN_REQUIRED:
          logging.warning('{} needs to be logged in.'.format(
              profile_path_name(profile_path)))
    if got in (OK, AIRBNB_IS_DOWN):
      browser.close()