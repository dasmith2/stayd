from datetime import timedelta
from unittest.mock import Mock, call

from work.api import API
from work.models.fixed_or_flexible import FIXED, FLEXIBLE
from work.models.one_off import (
    OneOff, LineItem, disable_old_checklists_background)
from work.tests.test_maintenance_checklist import (
    get_test_maintenance_checklist)
from work.tests.test_rental import get_test_properly_rental
from work.tests.test_work import (
    get_test_independent_worker, set_work_stuff)
from work.tests.test_work_type import get_test_work_type
from util.tests import TestCase, FakeResponse
from util.timezone import str_to_tz_dt, now


def get_test_one_off(**kwargs):
  properly_rental = kwargs.get('properly_rental', None)
  if not properly_rental:
    if 'rental' in kwargs:
      properly_rental = kwargs['rental'].properlyrental_or_none
  if not properly_rental:
    properly_rental = get_test_properly_rental(**kwargs)

  one_off = OneOff(
      title=kwargs.get('title', 'Tiny little title'),
      message=kwargs.get('message', 'Do a good job ok everybody?'),
      properly_rental=properly_rental,
      bill_to_building=kwargs.get('bill_to_building', None),
      work_type=kwargs.get('work_type', None),
      end_time=kwargs.get('end_time', None),
      expected_duration=kwargs.get('expected_duration', 3),
      checklist=kwargs.get('checklist', None),
      existing_checklist_url=kwargs.get('existing_checklist_url', None),
      offered_start_time=kwargs.get(
          'offered_start_time', str_to_tz_dt('2018-10-15 14:00')))
  set_work_stuff(one_off, **kwargs)
  return one_off


def get_test_line_item(**kwargs):
  one_off = kwargs.get('one_off', None)
  if not one_off:
    one_off = get_test_one_off(**kwargs)
  return LineItem.objects.create(
      one_off=one_off,
      description=kwargs.get('description', 'Do stuff!'))


class OneOffTests(TestCase):
  def test_duplicate(self):
    # I know we'll never get a one off with both line items AND
    # existing_checklist_url in real life, but I'm lazy and want to check that
    # both get duplicated.
    bob = get_test_independent_worker()
    original = get_test_one_off(
        title='Sticks you get hit with',
        message='Post apocalyptic prep',
        work_type=None,  # When the work type is none, copy offered to.
        offered_start_time=str_to_tz_dt('2019-01-15 12:00'),
        end_time=str_to_tz_dt('2019-01-15 14:00'),
        expected_duration=2,
        existing_checklist_url='properly.com/#/checklists/gross/tellMeMore/',
        fixed_or_flexible=FIXED,
        offered_to=[bob])
    # Hacking the auto populated created_at field to pretend the original got
    # made 1 day ago, meaning this was scheduled for 2 days after it was
    # created.
    OneOff.objects.filter(pk=original.pk).update(
        created_at=now() - timedelta(hours=24))
    get_test_line_item(one_off=original, description='Lived to blog about it')

    duplicated = original.duplicate(nnow=str_to_tz_dt('2019-01-20 11:00'))

    self.assertEqual('Sticks you get hit with', duplicated.title)
    self.assertEqual('Post apocalyptic prep', duplicated.message)
    self.assertIsNone(duplicated.work_type)
    # Let this also be scheduled 2 days after it was created moments ago.
    self.assertEqual(
        str_to_tz_dt('2019-01-20 11:00'), duplicated.offered_start_time)
    self.assertEqual(
        str_to_tz_dt('2019-01-20 13:00'), duplicated.end_time)
    self.assertEqual(2, duplicated.expected_duration)
    self.assertEqual(
        'properly.com/#/checklists/gross/tellMeMore/',
        duplicated.existing_checklist_url)
    self.assertEqual(FIXED, duplicated.fixed_or_flexible)
    duplicated.lineitem_set.get(description='Lived to blog about it')
    self.assertEqual(1, duplicated.offered_to.count())
    self.assertEqual(
        bob, duplicated.offered_to.first().get_child_class_instance())

  def test_available_workers(self):
    work_type = get_test_work_type()
    properly_rental = get_test_properly_rental()
    fatima = get_test_independent_worker(
        work_types=[work_type], buildings=[properly_rental.rental.building])
    bill = get_test_independent_worker(
        work_types=[work_type], buildings=[properly_rental.rental.building])
    get_test_one_off(
        accepted_by=fatima, fixed_or_flexible=FLEXIBLE,
        offered_start_time=str_to_tz_dt('2018-01-15 12:00'),
        properly_rental=properly_rental, work_type=work_type)
    flexible = get_test_one_off(
        fixed_or_flexible=FLEXIBLE,
        offered_start_time=str_to_tz_dt('2018-01-15 12:00'),
        properly_rental=properly_rental, work_type=work_type)
    self.assertEqual(set([fatima, bill]), set(flexible.should_offer_to()))

    get_test_one_off(
        accepted_by=fatima, fixed_or_flexible=FIXED,
        offered_start_time=str_to_tz_dt('2018-01-16 12:00'),
        properly_rental=properly_rental, work_type=work_type)
    fixed = get_test_one_off(
        fixed_or_flexible=FIXED,
        offered_start_time=str_to_tz_dt('2018-01-16 12:00'),
        properly_rental=properly_rental, work_type=work_type)
    self.assertEqual(set([bill]), set(fixed.should_offer_to()))

  def test_disable_old_checklists(self):
    """ I'm testing this here because it's really about disabling one off
    checklists. And it makes more sense here if we ever want to move Checklist
    somewhere else. """
    no1 = get_test_maintenance_checklist(checklist_id='no_one_off')
    disable_checklist = get_test_maintenance_checklist(
        checklist_id='disable_me')
    get_test_one_off(
        checklist=disable_checklist,
        offered_start_time=str_to_tz_dt('2018-09-15 12:00'))
    too_soon_to_disable = get_test_maintenance_checklist(
        checklist_id='too_soon')
    get_test_one_off(
        checklist=too_soon_to_disable,
        offered_start_time=str_to_tz_dt('2018-10-14 12:00'))

    api = Mock(spec=API)
    api.checklist_disable.return_value = FakeResponse(True, {})
    nnow = str_to_tz_dt('2018-10-15 12:00')
    disable_old_checklists_background(api=api, nnow=nnow)

    no1.refresh_from_db()
    disable_checklist.refresh_from_db()
    too_soon_to_disable.refresh_from_db()
    self.assertIsNone(no1.disabled_at)
    self.assertIsNotNone(disable_checklist.disabled_at)
    self.assertIsNone(too_soon_to_disable.disabled_at)

    self.assertEqual(
        [call('disable_me')], api.checklist_disable.call_args_list)
