from django.core.management.base import BaseCommand
from selenium.common.exceptions import SessionNotCreatedException

from listings.api import AirvatarAPI
from scrape.airbnb_scraper import AirbnbScraper
from scrape.browser import Browser, WEBSITE_DOWN, OK

LISTINGS = 'listings'
RESERVATIONS = 'reservations'


class Command(BaseCommand):
  help = 'Scrape listings, reservations, and payouts off Airbnb.'

  def add_arguments(self, parser):
    parser.add_argument(
        'action', choices=[LISTINGS, RESERVATIONS], help=(
            'Specifying reservations pulls down Paypal payouts and '
            'paid out reservations.'))
    parser.add_argument('--airvatar', help=(
        'The name of a single airvatar. If none is specified, it runs for '
        'all airvatars.'))

  def handle(self, *args, **options):
    """ If we get an unexpected ERROR or a good ol' fashioned crash, the
    browser should stay up and progress should halt so we can figure out what
    the heck happened and fix it. If WEBSITE_DOWN, halt progress but also
    close the browser. If we're OK, keep going, unless we're done, in which
    case close the browser. TODO(Dave) A command to scrape whoever needs it.
    """
    airvatar_api = AirvatarAPI()
    got = OK
    if options['airvatar']:
      airvatars = [airvatar_api.get(options['airvatar'])]
    else:
      airvatars = airvatar_api.all()
    for airvatar in airvatars:
      action = options['action']
      if action == LISTINGS:
        print('Scraping {}\'s listings'.format(airvatar.name))
      elif action == RESERVATIONS:
        print('Scraping {}\'s paid out reservations'.format(airvatar.name))
      browser = Browser(airvatar)
      browser.start()
      scraper = AirbnbScraper(browser)
      scraper.login()
      if action == LISTINGS:
        got = scraper.save_listings()
      elif action == RESERVATIONS:
        got = scraper.save_payouts_and_reservations()
      if got in (OK, WEBSITE_DOWN):
        try:
          browser.close()
        except SessionNotCreatedException:
          pass  # The user probably just closed the browser.
