import sys
from django.core.management.base import BaseCommand

from errors.models import log_error
from guest_messages.models import Message
from guesty.api import GuestySync


class Command(BaseCommand):
  help = 'Find all the guest messages that need sending and send them.'

  def add_arguments(self, parser):
    parser.add_argument(
        '--verbose', action='store_true', dest='verbose')

  def handle(self, *args, **options):
    verbose = options['verbose']
    try:
      Message.objects.send(GuestySync(), verbose=verbose)
    except Exception:
      log_error('send_guest_messages error', exc_info=sys.exc_info())
      if verbose:
        print(
            'There was an error. Check '
            'https://stayd-prod.herokuapp.com/admin/errors/stayderror/')
