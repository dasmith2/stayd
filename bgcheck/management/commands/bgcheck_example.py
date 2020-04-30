from util.channels import AIRBNB
from util.web_test_users import VIRTUAL_HOST_USERNAME
from util.web_test import WebTest, WebTestCommand


class Command(WebTestCommand):
  help = (
      'Run this from your local machine to create a fake Airbnb reservation '
      'that requires a background check and open a browser to the id '
      'verification page. This way you can show somebody how the id '
      'verification flow works when a background check is required.')

  def web_test_classes(self):
    return [BGCheckWebExample]


class BGCheckWebExample(WebTest):
  def run(self):
    reservation_data = self.get_bg_check_reservation_data(AIRBNB)
    self.open_id_verify(reservation_data['channel_id'])

  def get_bg_check_reservation_data(self, channel):
    return self.server_json('get_bg_check_reservation_data', channel=channel)

  def open_id_verify(self, channel_id):
    query_string = 'id={}'.format(channel_id)
    self.server_get(
        'verify_id', VIRTUAL_HOST_USERNAME, query_string=query_string)
