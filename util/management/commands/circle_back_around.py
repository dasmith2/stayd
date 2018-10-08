from commands.stayd_command import StaydCommand
from guest_messages.models.models import RawMandrillEvent
from guesty.guesty import Guesty
from reservations.models import Reservation
from reservations.syncer import ReservationManagerIsDown


class Command(StaydCommand):
  help = (
      'Sometimes Front, or Guesty, or whatever goes down for a moment and '
      'we can\'t complete a task. This regularly run command is the one that '
      'circles back around and retries that stuff.')

  def run(self, verbose):
    try:
      RawMandrillEvent.objects.rerun_webhooks(verbose=verbose)
      Guesty().handle_raw_events(verbose=verbose)
      Reservation.objects.sync_expecting_payments()
    except ReservationManagerIsDown:
      pass

  def name(self):
    return 'circle_back_around'
