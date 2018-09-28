from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils.timezone import now

from guesty.guesty import Guesty
from guest_messages.models.models import RawMandrillEvent
from guesty.models import RawEvent


class Command(BaseCommand):
  help = (
      'RawEvents are created when a Guesty webhook runs. If they aren\'t '
      'successful, we get notified, and we still have the json. This '
      'function reruns failed webhooks from the past 24 hours. It\'s useful '
      'when you\'ve deployed a fix.')

  def handle(self, *args, **options):
    self._rerun_guesty()
    self._rerun_mandrill()

  def _rerun_guesty(self):
    sync = Guesty()
    for event in RawEvent.objects.filter(
        created_at__gte=now() - timedelta(days=1), handled_at__isnull=True):
      if event.check_404_reservation():
        print('This reservation is a 404.')
      else:
        handled = sync.handle_raw_event(event)
        if handled:
          print(handled)

  def _rerun_mandrill(self):
    RawMandrillEvent.objects.rerun_webhooks(verbose=True)
