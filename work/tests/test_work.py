from work.models.fixed_or_flexible import FIXED, FLEXIBLE
from work.models.work import Work
from work.tests.test_worker import get_test_independent_worker
from util.tests import TestCase
from util.timezone import str_to_tz_dt


def set_work_stuff(work, **kwargs):
  work.accepted_by = kwargs.get('accepted_by', None)
  work.job_request_id = kwargs.get('job_request_id', '')
  work.creation_confirmed = kwargs.get('creation_confirmed', None)
  work.creation_error = kwargs.get('creation_error', '')
  work.offered_start_time = kwargs.get('offered_start_time', None)
  work.deadline = kwargs.get('deadline', None)
  work.accepted_at = kwargs.get('accepted_at', None)
  work.started_at = kwargs.get('started_at', None)
  work.completed_at = kwargs.get('completed_at', None)
  work.canceled_at = kwargs.get('canceled_at', None)
  work.permanently_canceled_reason = kwargs.get(
      'permanently_canceled_reason', '')
  work.all_tasks_complete = kwargs.get('all_tasks_complete', True)
  work.fixed_or_flexible = kwargs.get('fixed_or_flexible', FIXED)
  work.action_on_properly = kwargs.get('action_on_properly', False)
  work.action_on_keys = kwargs.get('action_on_keys', False)
  work.save()
  for worker in kwargs.get('offered_to', []):
    work.offered_to.add(worker)
  if 'created_at' in kwargs:
    Work.objects.filter(pk=work.pk).update(created_at=kwargs['created_at'])
    work.refresh_from_db()
  return work


class WorkTests(TestCase):
  def test_send_good_morning_todays_jobs_to(self):
    from work.tests.test_cleaning import get_test_cleaning
    from work.tests.test_maintenance import get_test_maintenance
    akua = get_test_independent_worker(name='Akua Sar')
    bob = get_test_independent_worker(name='Bob Slob')
    cleaning = get_test_cleaning(
        offered_to=[akua, bob], offered_start_time=str_to_tz_dt('2018-12-25'))
    alerted = cleaning.send_good_morning_todays_jobs_to()
    self.assertEqual(
        set([akua, bob]), set([
            cleaner.get_child_class_instance() for cleaner in alerted]))
    cleaning.accepted_by = akua
    cleaning.save()
    self.assertEqual([akua], cleaning.send_good_morning_todays_jobs_to())
    maintenance = get_test_maintenance(
        offered_to=[akua, bob], offered_start_time=str_to_tz_dt('2018-12-25'))
    sent_to = maintenance.send_good_morning_todays_jobs_to()
    sent_to_child_classes = [
        worker.get_child_class_instance() for worker in sent_to]
    self.assertEqual(set([akua, bob]), set(sent_to_child_classes))

  def test_overlapping(self):
    from work.tests.test_one_off import get_test_one_off
    from work.tests.test_cleaning import (
        get_test_cleaning, get_test_cleaning_config)
    worker = get_test_independent_worker()
    different_worker = get_test_independent_worker()
    fixed_one_off = get_test_one_off(
        offered_start_time=str_to_tz_dt('2019-01-01 12:00'),
        accepted_by=worker, fixed_or_flexible=FIXED, expected_duration=3,
        offered_to=[worker, different_worker])
    cleaning = get_test_cleaning(
        accepted_by=worker,
        offered_start_time=str_to_tz_dt('2019-01-01 13:00'),
        offered_to=[worker, different_worker])
    get_test_cleaning_config(rental=cleaning.reservation.rental)
    get_test_one_off(  # different_day
        offered_start_time=str_to_tz_dt('2019-01-02 12:00'),
        accepted_by=worker, fixed_or_flexible=FIXED, expected_duration=3,
        offered_to=[worker, different_worker])
    get_test_one_off(  # different_worker
        offered_start_time=str_to_tz_dt('2019-01-01 12:00'),
        accepted_by=different_worker, fixed_or_flexible=FIXED,
        expected_duration=3, offered_to=[worker, different_worker])
    flexible_one_off = get_test_one_off(
        offered_start_time=str_to_tz_dt('2019-01-01 13:00'),
        accepted_by=worker, fixed_or_flexible=FLEXIBLE, expected_duration=3,
        offered_to=[worker, different_worker])

    not_accepted = get_test_one_off(
        offered_start_time=str_to_tz_dt('2019-01-01 12:00'),
        fixed_or_flexible=FIXED, expected_duration=3,
        offered_to=[worker, different_worker])
    get_test_one_off(  # Not offered to worker
        offered_start_time=str_to_tz_dt('2019-01-01 12:00'),
        fixed_or_flexible=FIXED, expected_duration=3,
        offered_to=[different_worker])

    self.assertEqual([], flexible_one_off.overlapping_accepted())
    self.assertEqual([fixed_one_off], cleaning.overlapping_accepted())
    self.assertEqual([cleaning], fixed_one_off.overlapping_accepted())
    self.assertEqual([not_accepted], fixed_one_off.overlapping_offers())
