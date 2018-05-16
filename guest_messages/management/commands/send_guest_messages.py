from django.core.management.base import BaseCommand

from guest_messages.models import Message


class Command(BaseCommand):
  help = 'Find all the guest messages that need sending and send them.'

  def add_arguments(self, parser):
    parser.add_argument(
        '--verbose', action='store_true', dest='verbose')

  def handle(self, *args, **options):
    Message.objects.send(verbose=options['verbose'])
