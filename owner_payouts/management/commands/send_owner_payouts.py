from django.core.management.base import BaseCommand

from owner_payouts.models import OwnerPayout


class Command(BaseCommand):
  help = (
      'Send all green-lit, unsent owner payouts with a send date on or '
      'before today.')

  def add_arguments(self, parser):
    parser.add_argument(
        '--verbose', action='store_true', dest='verbose')

  def handle(self, *args, **options):
    OwnerPayout.objects.send(verbose=options['verbose'])
