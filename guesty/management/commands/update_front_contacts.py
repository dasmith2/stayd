from commands.stayd_command import StaydCommand
from guesty.front_contact_updater import FrontContactUpdater


class Command(StaydCommand):
  help = (
      'When a guest messages us, that shows up in Front. Update contact '
      'information for all guest phone numbers for upcoming reservations '
      'so if any of them SMS us, we can instantly know who they are and '
      'where they\'re staying.')

  def run(self, verbose):
    FrontContactUpdater().update(verbose=verbose)

  def name(self):
    return 'update_front_contacts'
