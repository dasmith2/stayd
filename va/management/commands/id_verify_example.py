from util.channels import AIRBNB
from util.web_test import WebTest, WebTestCommand
from va.management.commands.id_verify_helper import IDVerifyHelper


class Command(WebTestCommand):
  help = (
      'Run this from your local machine. '
      'It creates an entirely new ID submission on --server and opens up the '
      'ID verification page so you can play around with it.')

  def web_test_classes(self):
    return [IDVerifyExample]


class IDVerifyExample(WebTest):
  def run(self):
    helper = IDVerifyHelper(self)
    helper.open_id_verify()

  def open_id_verify(self, channel=AIRBNB):
    self.get_test_reservation(channel=channel)
    self.get('{}?id={}'.format(
        self.server_reverse('verify_id'), self.channel_id))

  def get_test_reservation(self, channel=AIRBNB):
    got = self.server_json(
        'get_reservation_for_id_verify_test', channel=channel)
    self.channel_id = got['channel_id']
    self.guest_first_name = got['guest_first_name']
    self.guest_full_name = got['guest_full_name']
