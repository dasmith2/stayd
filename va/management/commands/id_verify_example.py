from util.web_test import WebTest, WebTestCommand


class Command(WebTestCommand):
  help = (
      'Run this from your local machine. '
      'It creates an entirely new ID submission on --server and opens up the '
      'ID verification page so you can play around with it.')

  def web_test_classes(self):
    return [IDVerifyWebExample]


class IDVerifyWebExample(WebTest):
  def run(self):
    self.open_id_verify()

  def open_id_verify(self):
    self.get_test_reservation()
    self.get('{}?id={}'.format(
        self.server_reverse('verify_id'), self.channel_id))

  def get_test_reservation(self):
    got = self.server_json('get_reservation_for_id_verify_test')
    self.channel_id = got['channel_id']
    self.guest_first_name = got['guest_first_name']
    self.guest_full_name = got['guest_full_name']
