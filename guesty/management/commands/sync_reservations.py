from django.core.management.base import BaseCommand

from guesty.api import GuestyAPI


class Command(BaseCommand):
  help = 'Sync all reservations from Guesty'

  def handle(self, *args, **options):
    GuestyAPI().sync_reservations()
