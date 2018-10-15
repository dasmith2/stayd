from commands.stayd_command import StaydCommand
from front.models import Front
from guest_messages.models.models import RawMandrillEvent
from guesty.guesty import Guesty
from id_verify.models import Submission
from reservations.models import Reservation
from reservations.syncer import ReservationManagerIsDown


class Command(StaydCommand):
  help = (
      'Sometimes Front, or Guesty, or whatever goes down for a moment and '
      'we can\'t complete a task. This regularly run command is the one that '
      'circles back around and retries that stuff.')

  def run(self, verbose):
    try:
      if verbose:
        print('RawMandrillEvent.objects.rerun_webhooks')
      RawMandrillEvent.objects.rerun_webhooks(verbose=verbose)
      if verbose:
        print('Guesty().handle_raw_events')
      Guesty().handle_raw_events(verbose=verbose)
      if verbose:
        print(
            'Submission.objects.'
            'match_reservations_to_reservationless_submissions')
      Submission.objects.match_reservations_to_reservationless_submissions(
          verbose=verbose)
      if verbose:
        print('Front().circle_back_around_failed_contact_info_pushes')
      Front().circle_back_around_failed_contact_info_pushes(verbose=verbose)
      # This one takes a while so I do it last in case anybody is watching.
      if verbose:
        print('Reservation.objects.sync_expecting_payments')
      Reservation.objects.sync_expecting_payments()
    except ReservationManagerIsDown:
      pass

  def name(self):
    return 'circle_back_around'
