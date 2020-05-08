"""
pip install selenium
"""
from va.management.commands.id_verify_example import IDVerifyExample
from va.management.commands.id_verify_helper import IDVerifyHelper
from util.web_test import WebTestCommand


class Command(WebTestCommand):
  help = (
      'Run this from your local machine. '
      'It creates an entirely new ID submission on --server and verifies it.')

  def web_test_classes(self):
    return [IDVerifyWebTest]


class IDVerifyWebTest(IDVerifyExample):
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
    self.helper = IDVerifyHelper(self)
    self.helper.open_id_verify()
    self._submit_an_id()
    self.helper.approve_id(self.helper.guest_full_name)

  def _submit_an_id(self):
    """ We auto scroll the page for the user. If you go so fast that you
    get two scroll animations at the same time, the page jumps frantically and
    the test is a mess to watch. Ideally these tests verify but also reasure.
    So just put a bit of sleep on navigation events. """
    h1 = self.driver.find_element_by_tag_name('h1')
    assert self.helper.guest_first_name in h1.text
    assert h1.is_displayed()
    self.helper.click_get_started()
    use_guest_phone = self.helper.use_guest_phone()
    assert use_guest_phone.is_displayed()
    use_guest_phone.click()
    self.wait_a_sec()
    email = self.get_active_element()  # Should be email anyway.
    assert 'email' == email.get_attribute('id')
    assert email.is_displayed()
    self.helper.enter_email('test@test.com')

    self.helper.do_file_upload('panel-id', self.img_path('ny_id_front.jpg'))
    self.click_button('panel-id')

    self.helper.done()
