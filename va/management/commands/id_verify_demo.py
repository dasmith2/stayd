from va.management.commands.id_verify_helper import IDVerifyHelper
from va.management.commands.id_verify_example import IDVerifyExample
from util.channels import BOOKINGCOM
from util.web_test import WebTestCommand


class Command(WebTestCommand):
  help = (
      'Run this from your local machine to demo simple ID verification.')

  def web_test_classes(self):
    return [IDVerifyDemo]


class IDVerifyDemo(IDVerifyExample):
  def run(self):
    """
    Ask stage to get some upcoming reservation from Guesty with a checkin in
    the upcoming month, clear out any existing submissions, and return the
    guesty id.
    Sync that reservation locally.
    Pop open selenium.
    Go to https://stage.stayd.com/verify_id/ for that reservation.
    Complete the id submission.
    Log into https://stage.stayd.com/verify_id/submissions with
    username: systemtest password: 97d2mk.Y
    Approve the submission.
    Verify that it's not in the list any more.
    """
    helper = IDVerifyHelper(self)
    helper.open_id_verify(channel=BOOKINGCOM)
    import pdb
    pdb.set_trace()
    helper.get_approve_id_container(helper.guest_full_name)
