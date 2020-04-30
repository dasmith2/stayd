from djmoney.money import Money

from work.models.work_type import WorkType, CLEANER
from work.models.worker import IndependentWorker
from work.tests.test_work_type import get_test_work_type
from rentals.tests import get_test_building, get_test_rental
from util.random_string import random_string
from util.tests import TestCase
from util.timezone import str_to_tz_dt


def get_test_independent_worker(**kwargs):
  worker = IndependentWorker(
      hour_rate=kwargs.get('hour_rate', Money('15.0', 'USD')),
      hour_min=kwargs.get('hour_min', 1),
      full_time_employee=kwargs.get('full_time_employee', False))
  set_worker_stuff(worker, **kwargs)
  for building in kwargs.get('buildings', []):
    worker.buildings.add(building)
  return worker


def set_worker_stuff(worker, **kwargs):
  if 'user' in kwargs:
    raise Exception(
        'IndependentWorker no longer has user. Worker has base_user')
  worker.email = kwargs.get('email', '{}@email.email'.format(random_string(5)))
  worker.name = kwargs.get('name', 'Mr Clean ' + random_string(5))
  worker.phone = kwargs.get('phone', '555-555-5555')
  worker.worker_id = kwargs.get('worker_id', None)
  worker.base_user = kwargs.get('base_user', None)
  worker.save()
  for work_type in kwargs.get('work_types', [
      WorkType.objects.get_work_type(CLEANER)]):
    if isinstance(work_type, WorkType):
      worker.work_types.add(work_type)
    elif isinstance(work_type, str):
      worker.work_types.add(WorkType.objects.get_work_type(work_type))
    else:
      raise Exception(work_type.__class__)


class WorkerTests(TestCase):
  def test_available(self):
    from work.tests.test_cleaning import (
        get_test_cleaning, get_test_cleaning_config)
    building = get_test_building()
    rental = get_test_rental(building=building)
    get_test_cleaning_config(rental=rental)
    cleaning = get_test_work_type(name='Cleaning')
    destroying = get_test_work_type(name='Destroying')
    bob = get_test_independent_worker(
        buildings=[building], work_types=[cleaning], name='Bob slob')
    get_test_cleaning(
        check_in=str_to_tz_dt('2018-10-14 16:00'),
        check_out=str_to_tz_dt('2018-10-15 11:00'), rental=rental,
        accepted_by=bob)
    self.assertEqual([bob], IndependentWorker.objects.available(
        str_to_tz_dt('2018-10-15 10:00'), 1, building, cleaning))
    # The new job ends during the old job.
    self.assertEqual([], IndependentWorker.objects.available(
        str_to_tz_dt('2018-10-15 10:00'), 2, building, cleaning))
    self.assertEqual(  # A work type that bob can't do
        [], IndependentWorker.objects.available(
            str_to_tz_dt('2018-10-15 10:00'), 1, building, destroying))
    self.assertEqual(  # The new job starts during the old job.
        [], IndependentWorker.objects.available(
            str_to_tz_dt('2018-10-15 12:00'), 1, building, cleaning))
    self.assertEqual(  # Different building.
        [], IndependentWorker.objects.available(
            str_to_tz_dt('2018-10-15 10:00'), 1, get_test_building(),
            cleaning))
    self.assertEqual(
        [bob], IndependentWorker.objects.available(
            str_to_tz_dt('2018-10-15 16:00'), 1, building, cleaning))


class IndependentWorkerLookupTests(TestCase):
  def setUp(self):
    super().setUp()
    self.building_1 = get_test_building()
    self.building_2 = get_test_building()
    self.work_type_1 = get_test_work_type()
    self.work_type_2 = get_test_work_type()
    self.bob = get_test_independent_worker(
        buildings=[self.building_1, self.building_2],
        work_types=[self.work_type_1])
    self.fatima = get_test_independent_worker(
        buildings=[self.building_1],
        work_types=[self.work_type_2])
    get_test_independent_worker(work_types=[get_test_work_type()])

  def test_get_building_work_type_lookup(self):
    expected = {
        self.building_1: set([self.work_type_1, self.work_type_2]),
        self.building_2: set([self.work_type_1])}
    self.assertEqual(
        expected,
        IndependentWorker.objects.get_building_work_type_lookup())

  def test_get_building_worker_lookup(self):
    expected = {
        self.building_1: set([self.bob, self.fatima]),
        self.building_2: set([self.bob])}
    self.assertEqual(
        expected,
        IndependentWorker.objects.get_building_worker_lookup())
