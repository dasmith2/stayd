"""
You can see in guesty/api_getter.py that only prod can write to
Guesty. front/models.py and guest_messages/mandrill.py don't send
messages on stage.

pip install selenium
"""
import requests

from django.shortcuts import reverse

from guesty.api import sync_reservation

from commands.stayd_command import StaydCommand


class Command(StaydCommand):
  help = (
      'Run this from your local machine. '
      'It creates an entirely new ID submission in stage and verifies it.')

  def run(self, verbose):
    """
    Ask stage to get some upcoming reservation from Guesty with a checkin in
    the upcoming month, clear out any existing submissions, and return the
    guesty id.
    Sync that reservation.
    Pop open selenium.
    Go to https://stage.stayd.com/verify_id/ for that reservation.
    Complete the id submission.
    Log into https://stage.stayd.com/verify_id/submissions with
    username: systemtest password: 97d2mk.Y
    Approve the submission.
    Verify that it's not in the list any more.
    """
    url = 'https://stage.stayd.com{}'.format(
        reverse('get_reservation_for_system_test'))
    guesty_id = requests.get(url).json()['guesty_id']
    sync_reservation(guesty_id)

  def name(self):
    return 'id_verify system_test'
