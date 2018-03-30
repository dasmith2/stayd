from django.core.management.base import BaseCommand

from vreasy.models import VreasyLoader
from vreasy.api import VreasyAPI


WHAT_TO_PULL = 'what_to_pull'
PROPERTIES = 'properties'
RESERVATIONS = 'reservations'


class Command(BaseCommand):
  help = 'Pull information from vreasy.'

  def add_arguments(self, parser):
    parser.add_argument(
        WHAT_TO_PULL, choices=[PROPERTIES, RESERVATIONS], help=(
            'Specifying properties pulls down Vreasy\'s properties which must '
            'then be linked up with our Rental objects in our vreasy django '
            'admin. Specifying reservations pulls down as much information '
            'as possible, which isn\'t much, about our reservations from '
            'vreasy.'))

  def handle(self, *args, **options):
    loader = VreasyLoader(VreasyAPI())
    if options[WHAT_TO_PULL] == PROPERTIES:
      loader.pull_properties()
    elif options[WHAT_TO_PULL] == RESERVATIONS:
      loader.pull_recent_reservations()
