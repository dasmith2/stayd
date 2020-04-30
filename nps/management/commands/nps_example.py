from util.web_test import WebTest, WebTestCommand


class Command(WebTestCommand):
  help = 'Run this from your local machine to show how our guests can rate us.'

  def web_test_classes(self):
    return [NPSExample]


class NPSExample(WebTest):
  def run(self):
    self.open_rate_us()

  def open_rate_us(self, score=9):
    self.server_get(
        'rate_us', None, query_string='?score={}'.format(score),
        channel_id=self.get_test_channel_id())

  def get_test_channel_id(self):
    return self.server_json('get_test_nps_channel_id')['channel_id']
