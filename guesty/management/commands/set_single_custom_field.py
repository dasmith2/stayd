from datetime import timedelta

from django.core.management.base import BaseCommand
from util.timezone import now

from guesty.guesty import GuestyAPI
from guesty.models import GuestyReservation


class Command(BaseCommand):
  help = 'At this point, this command sets the Guest feedback request field.'

  def handle(self, *args, **options):
    cutoff = now() - timedelta(days=3)
    for guesty_res in GuestyReservation.objects.filter(
        reservation__check_out__gte=cutoff):
      print('Updating {}'.format(guesty_res.guesty_id))
      custom_fields = guesty_res.get_custom_fields()
      custom_fields.set('5b299253f2177301cca1269a', True)
      custom_fields.send_changes(GuestyAPI())
