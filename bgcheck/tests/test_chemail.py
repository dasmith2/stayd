from unittest.mock import Mock, call

from django.conf import settings

from bgcheck.models.chemail import Chemail, send_chemails_background
from bgcheck.tests.test_background_check import SubmissionTests
from guest_messages.mandrill import Emailer
from util.timezone import str_to_tz_dt


class ChemailTests(SubmissionTests):
  def setUp(self):
    super().setUp()
    self.emailer = Mock(spec=Emailer)

  def test_failed_send_email(self):
    self.check.passed = False
    self.check.got_valid_submission_at = str_to_tz_dt('2018-12-23')
    self.check.completed_at = str_to_tz_dt('2018-12-24 23:00')
    self.check.save()

    # DON'T send it right away in case the VA clicked the wrong button.
    send_chemails_background(nnow=str_to_tz_dt('2018-12-24 23:59'))
    # Also don't try to catch up on old checks when I deploy
    send_chemails_background(nnow=str_to_tz_dt('2019-01-01'))
    self.assertFalse(Chemail.objects.exists())

    for i in range(2):
      send_chemails_background(
          nnow=str_to_tz_dt('2018-12-25 00:00'), emailer=self.emailer)

    subject = (
        'Regarding your recent reservation at Blarghs Hidey Hole in '
        'Excitingtown, ND with Howard')
    expected = call(
        subject, 'davery@doo.dave', {'guest_first': 'Davery'},
        settings.TEMPLATE_WE_MUST_CANCEL_DUE_TO_BGCHECK,
        ok_to_do_it_in_dev=False)
    self.assertEqual(
        [expected], self.emailer.send_email.call_args_list)
    Chemail.objects.get(reservation=self.reservation, to='davery@doo.dave')
    self.assertEqual(1, Chemail.objects.count())

  def test_fine_no_email(self):
    self.check.passed = True
    self.check.got_valid_submission_at = str_to_tz_dt('2018-12-23')
    self.check.completed_at = str_to_tz_dt('2018-12-24 23:00')
    self.check.save()

    send_chemails_background(
        nnow=str_to_tz_dt('2018-12-25 00:00'), emailer=self.emailer)

    self.assertEqual(0, len(self.emailer.send_email.call_args_list))
