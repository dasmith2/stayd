from django.core.management.base import BaseCommand
from reservations.models import Reservation
from scrape.airbnb_scraper import AirbnbScraper, RESERVATION_URL
from scrape.browser import Browser


LISTINGS = 'listings'
RESERVATIONS = 'reservations'


class Command(BaseCommand):
  help = 'Open a reservation or listing with the correct Airvatar'

  def add_arguments(self, parser):
    parser.add_argument(
        'id', help=(
            'You can put a reservation id, an address, a title, or an '
            'airvatar name.'))

  def handle(self, *args, **options):
    id = options['id']
    reservations = Reservation.objects.filter(channel_reservation_id=id)
    if reservations:
      reservation = reservations[0]
      airvatar = reservation.listing.airvatar
      browser = Browser(airvatar)
      browser.start()
      scraper = AirbnbScraper(browser)
      scraper.login()
      browser.get(RESERVATION_URL.format(id))

