from commands.stayd_command import StaydCommand
from id_verify.models import Submission


class Command(StaydCommand):
  help = (
      'Users are gonna upload huge photos of their IDs. This goes through '
      'and makes everything a more maneagable size. Users are also gonna '
      'upload images without clicking submit, causing orphan submissions. '
      'This will clean those up to. It also cleans up photos that are so '
      'old we don\'t need them anymore.')

  def run(self, verbose):
    Submission.objects.resize(verbose=verbose)
    Submission.objects.remove_unnecessary_images(verbose=verbose)

  def name(self):
    return 'resize_and_clean_up_id_images'
