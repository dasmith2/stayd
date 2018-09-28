from django.core.management.base import BaseCommand

from guesty.guesty import Guesty


class Command(BaseCommand):
  help = 'Sync all rentals from Guesty'

  def add_arguments(self, parser):
    parser.add_argument(
        '--verbose', action='store_true', dest='verbose')

  def handle(self, *args, **options):
    Guesty().sync_rentals(verbose=options['verbose'])
