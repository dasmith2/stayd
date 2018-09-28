from django.conf import settings
from django.core.management.base import BaseCommand

from guesty.guesty import Guesty


class Command(BaseCommand):
  help = 'Sync webhooks so this server receives updates from Guesty'

  def add_arguments(self, parser):
    parser.add_argument(
        '--verbose', action='store_true', dest='verbose')

  def handle(self, *args, **options):
    if not settings.THIS_SERVERS_BASE_URL_SET:
      raise Exception(
          'You need to set the THIS_SERVERS_BASE_URL environment variable '
          'for this to work.')
    Guesty().sync_webhooks(
        settings.THIS_SERVERS_BASE_URL, verbose=options['verbose'])
