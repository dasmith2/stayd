from django.core.management.base import BaseCommand

from guesty.api import GuestyAPI


class Command(BaseCommand):
  help = 'Sync all reservations from Guesty'

  def add_arguments(self, parser):
    parser.add_argument(
        '--verbose', action='store_true', dest='print_progress')

  def handle(self, *args, **options):
    GuestyAPI().sync_reservations(print_progress=options['print_progress'])
