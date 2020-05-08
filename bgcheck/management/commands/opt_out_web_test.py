from bgcheck.management.commands.bgcheck_example import BGCheckWebExample
from va.management.commands.id_verify_helper import IDVerifyHelper
from util.channels import AIRBNB
from util.web_test_users import VIRTUAL_HOST_USERNAME
from util.web_test import WebTestCommand


class Command(WebTestCommand):
  help = (
      'Run this from your local machine to test that guests can successfully '
      'opt-out of a background check, and that the staff will be informed '
      'to cancel and fully refund the reservation.')

  def web_test_classes(self):
    return [OptOutWebTest]


class OptOutWebTest(BGCheckWebExample):
  def run(self):
    channel_id = self.get_bg_check_reservation_data(AIRBNB)['channel_id']
    self.open_id_verify(channel_id)
    helper = IDVerifyHelper(self)

    helper.click_get_started()
    helper.use_guest_phone().click()
    self.wait_a_sec()
    helper.enter_email('test@test.com')

    opt_out_button = self.driver.find_element_by_id('opt-out-button')
    assert self.is_scrolled_to(opt_out_button)
    opt_out_button.click()
    self.wait_a_sec()

    confirm_opt_out_button = self.driver.find_element_by_id(
        'confirm-opt-out-button')
    confirm_opt_out_button.click()
    self.wait_a_sec()

    self.server_get('must_cancel', VIRTUAL_HOST_USERNAME)
    self.wait_for_text('//table', 'Dave Blave')
