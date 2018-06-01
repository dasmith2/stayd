from django.core.management.base import BaseCommand

from guesty.api import GuestySync


class Command(BaseCommand):
  help = 'Sync all listings from Guesty'

  def add_arguments(self, parser):
    parser.add_argument(
        '--verbose', action='store_true', dest='verbose')

  def handle(self, *args, **options):
    GuestySync().sync_listings(verbose=options['verbose'])
