from unittest.mock import Mock, call

from rentals.tests import get_test_building
from work.api import API
from work.models.abandoned import handle_abandoned_background
from work.models.message import (
    Message, MessageSender, NEVER_STARTED, NEVER_COMPLETED, EMAIL)
from work.models.repeat_work import RepeatWork
from work.tests.test_worker import get_test_independent_worker
from work.tests.test_repeat_work import (
    get_test_repeat_config, get_test_repeat_work)
from util.tests import TestCase
from util.timezone import str_to_tz_dt


class AbandonedTests(TestCase):
  def setUp(self):
    super().setUp()
    building = get_test_building(alerts_email='alert@building.com')
    self.repeat_config = get_test_repeat_config(
        guesty_id='sldfwensldslds', building=building)
    self.api = Mock(spec=API)
    self.scheduling_api = Mock()
    self.message_sender = Mock(spec=MessageSender)

  def test_do_nothing(self):
    get_test_repeat_work(  # Completed, even tho missing lots of fields
        job_request_id='a', repeat_config=self.repeat_config,
        offered_start_time=str_to_tz_dt('2018-10-02 00:00'),
        started_at=None, accepted_at=None, accepted_by=None,
        completed_at=str_to_tz_dt('2018-10-02 05:00'))
    get_test_repeat_work(  # Canceled, even tho missing lots of fields
        job_request_id='a', repeat_config=self.repeat_config,
        offered_start_time=str_to_tz_dt('2018-10-02 00:00'),
        started_at=None, accepted_at=None, accepted_by=None,
        canceled_at=str_to_tz_dt('2018-10-02 05:00'))
    created_today = get_test_repeat_work(
        job_request_id='', repeat_config=self.repeat_config,
        offered_start_time=str_to_tz_dt('2018-10-10 00:00'),
        started_at=None, accepted_at=None, accepted_by=None)

    handle_abandoned_background(
        nnow=str_to_tz_dt('2018-10-10 12:00'), properly_api=self.api,
        scheduling_api=self.scheduling_api, message_sender=self.message_sender)

    self.assertTrue(RepeatWork.objects.filter(pk=created_today.pk).exists())
    self.assertEqual([], self.api.job_request_cancel.call_args_list)

  def test_never_started(self):
    never_started = get_test_repeat_work(
        job_request_id='a', repeat_config=self.repeat_config,
        offered_start_time=str_to_tz_dt('2018-10-02 00:00'),
        accepted_by=None, accepted_at=None, started_at=None,
        completed_at=None, canceled_at=None)

    handle_abandoned_background(
        nnow=str_to_tz_dt('2018-10-15 12:00'), properly_api=self.api,
        scheduling_api=self.scheduling_api, message_sender=self.message_sender)
    never_started.refresh_from_db()

    message = Message.objects.get(
        to='alert@building.com', reason=NEVER_STARTED, kind=EMAIL,
        work=never_started)
    self.assertEqual([call(message)], self.message_sender.send.call_args_list)
    self.assertEqual(
        'Abandoned. Never started.',
        never_started.permanently_canceled_reason)

  def test_never_completed(self):
    never_completed = get_test_repeat_work(
        job_request_id='a', repeat_config=self.repeat_config,
        offered_start_time=str_to_tz_dt('2018-10-02 00:00'),
        accepted_by=get_test_independent_worker(),
        accepted_at=str_to_tz_dt('2018-10-01 12:00'),
        started_at=str_to_tz_dt('2018-10-02 01:00'), completed_at=None,
        canceled_at=None)

    for i in range(2):
      handle_abandoned_background(
          nnow=str_to_tz_dt('2018-10-15 12:00'), properly_api=self.api,
          scheduling_api=self.scheduling_api,
          message_sender=self.message_sender)

    self.assertEqual(0, len(self.api.job_request_cancel.call_args_list))
    message = Message.objects.get(
        to='alert@building.com', reason=NEVER_COMPLETED, kind=EMAIL,
        work=never_completed)
    self.assertEqual([call(message)], self.message_sender.send.call_args_list)
    self.assertEqual('', never_completed.permanently_canceled_reason)
