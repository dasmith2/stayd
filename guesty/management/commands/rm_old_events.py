from django.core.management.base import BaseCommand

from guesty.models import RawEvent


class Command(BaseCommand):
  help = (
      'RawEvents are created when a Guesty webhook runs. They build up '
      'over time so they have to be cleaned up. The command removes '
      'any that are older than 31 days.')

  def add_arguments(self, parser):
    parser.add_argument(
        '--verbose', action='store_true', dest='verbose')

  def handle(self, *args, **options):
    RawEvent.objects.rm_old(days_ago=31, verbose=options['verbose'])
