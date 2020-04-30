from commands.stayd_command import StaydCommand
from guest_messages.models.front_contact_updater import FrontContactUpdater
from guest_messages.models.email import RawMandrillEvent
from guesty.guesty import Guesty
from id_verify.models import Submission
from reservations.syncer import ReservationManagerIsDown
from util.background import background


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
        print(
            'FrontContactUpdater().'
            'circle_back_around_failed_contact_info_pushes')
      FrontContactUpdater().circle_back_around_failed_contact_info_pushes(
          verbose=verbose)
    except ReservationManagerIsDown:
      pass

  def name(self):
    return 'circle_back_around'


@background
def run_circle_back_around_background():
  Command().handle()
