import copy
from decimal import Decimal
import json

from rentals.tests import get_test_rental
from reservations.models import Reservation
from reservations.tests import get_test_reservation
from work.api_examples import CANCELED
from work.models.maintenance import (
    Maintenance, clean_up_empty_maintenance, busy)
from work.models.raw_event import RawEvent
from work.models.sla import NEXT_CHECKOUT, NEXT_VISIT
from work.models.work import FLEXIBLE
from work.tests.test_maintenance_checklist import (
    get_test_maintenance_checklist)
from work.tests.test_rental import get_test_properly_rental
from work.tests.test_work import set_work_stuff
from work.tests.test_work_type import get_test_work_type
from work.tests.test_worker import get_test_independent_worker
from util.signals import post_sync
from util.tests import TestCase
from util.timezone import str_to_tz_dt


def get_test_maintenance(**kwargs):
  maintenance = Maintenance(
      rental=kwargs.get('rental', None),
      title=kwargs.get('title', 'Do stuff'))
  return set_work_stuff(maintenance, **kwargs)


class CancelTests(TestCase):
  def setUp(self):
    super().setUp()
    self.maintenance = get_test_maintenance(
        offered_start_time=str_to_tz_dt('2018-12-24 11:15'),
        job_request_id='blue')

    self.hook = copy.deepcopy(CANCELED)
    self.hook['results'][0]['jobRequestId'] = 'blue'

  def test_action_on_properly_cancels(self):
    self.maintenance.action_on_properly = True
    self.maintenance.save()
    RawEvent.objects.create(json=json.dumps(self.hook)).handle()

    self.maintenance.refresh_from_db()
    self.assertIsNotNone(self.maintenance.canceled_at)

  def test_action_on_keys_dont_cancel(self):
    self.maintenance.action_on_keys = True
    self.maintenance.save()
    RawEvent.objects.create(json=json.dumps(self.hook)).handle()

    self.maintenance.refresh_from_db()
    self.assertIsNone(self.maintenance.canceled_at)


class CleanUpEmptyTests(TestCase):
  def test_clean_up_empty_maintenance(self):
    from work.tests.test_ticket import get_test_ticket

    delete_me_canceled = get_test_maintenance(
        offered_start_time=str_to_tz_dt('2018-12-24 11:15'),
        canceled_at=str_to_tz_dt('2018-12-24 11:00'), job_request_id='a')
    delete_me_offered = get_test_maintenance(
        offered_start_time=str_to_tz_dt('2018-12-24 11:15'),
        job_request_id='offered_maintenance_id')
    get_test_maintenance(  # hasnt_happened_yet
        offered_start_time=str_to_tz_dt('2018-12-25 11:15'),
        job_request_id='c')
    has_ticket = get_test_maintenance(
        offered_start_time=str_to_tz_dt('2018-12-24 11:15'),
        job_request_id='d')
    rental = get_test_rental()
    get_test_ticket(maintenance=has_ticket, rental=rental)
    get_test_maintenance(  # has_start_time
        offered_start_time=str_to_tz_dt('2018-12-24 11:15'),
        job_request_id='e', started_at=str_to_tz_dt('2018-12-24 11:15'))

    self.assertEqual(5, Maintenance.objects.count())
    clean_up_empty_maintenance(nnow=str_to_tz_dt('2018-12-25 01:00'))
    self.assertEqual(3, Maintenance.objects.count())
    self.assertEqual(0, Maintenance.objects.filter(
        pk__in=[delete_me_canceled.pk, delete_me_offered.pk]).count())


class CreateTests(TestCase):
  def setUp(self):
    super().setUp()

    from work.tests.test_ticket import get_test_ticket
    self.rental = get_test_rental()
    properly_rental = get_test_properly_rental(
        rental=self.rental, properly_property_id='NwlTE3dexN',
        source_property_id='NwlTE3dexN')
    work_type = get_test_work_type()
    self.worker = get_test_independent_worker(
        work_types=[work_type], buildings=[self.rental.building],
        email='test@independent.worker')
    self.maintenance = get_test_maintenance(
        offered_start_time=str_to_tz_dt('2018-12-26 11:15'),
        offered_to=[self.worker], fixed_or_flexible=FLEXIBLE,
        deadline=str_to_tz_dt('2018-12-26 15:45'))
    self.checklist = get_test_maintenance_checklist(
        properly_rental=properly_rental, title='Forced fun Fridays',
        items=['Do your darndest', 'Have fun with it'])
    self.forced_fun_fridays = get_test_ticket(
        sla=NEXT_CHECKOUT, checklist=self.checklist, work_type=work_type,
        maintenance=self.maintenance, rental=self.rental,
        created_at=str_to_tz_dt('2018-12-25 12:00'),
        title='Forced fun Fridays', expected_duration=Decimal(1.5),
        appendix='Cans of worms')
    existing_url = (
        'https://app.getproperly.com/#/checklists/SYEoYT5Gxi/ecbDE20WZ1/')
    get_test_ticket(
        sla=NEXT_VISIT, existing_checklist_url=existing_url,
        work_type=work_type, maintenance=self.maintenance, rental=self.rental,
        created_at=str_to_tz_dt('2018-12-25 12:00'),
        title='Careening towards your doom', expected_duration=Decimal(1),
        appendix='Love like you dont know how to read')

  def test_busy(self):
    self.assertFalse(busy(self.worker, nnow=str_to_tz_dt('2018-12-26 12:00')))
    self.maintenance.accepted_by = self.worker
    self.maintenance.started_at = str_to_tz_dt('2018-12-26 11:00')
    self.maintenance.save()
    self.assertTrue(busy(self.worker, nnow=str_to_tz_dt('2018-12-26 12:00')))

  def test_get_expected_duration(self):
    self.assertEqual(
        str_to_tz_dt('2018-12-26 11:15'), self.maintenance.get_start_time())
    self.assertEqual(
        str_to_tz_dt('2018-12-26 15:45'), self.maintenance.get_deadline())
    self.assertEqual(2.5, self.maintenance.get_expected_duration())
    self.forced_fun_fridays.expected_duration = Decimal(100)
    self.forced_fun_fridays.save()
    self.assertEqual(4.5, self.maintenance.get_expected_duration())

  def test_res_wraps_and_cancels_job(self):
    """ NEXT_CHECKOUT and NEXT_VACANT_NIGHT are typically (though not always!)
    scheduled immediately after a reservation. If that reservation gets
    canceled, we're in an uneasy state. Don't change the maintenance, but it's
    totally possible that a new reservation will get booked over the
    maintenance, in which case we'd have to cancel the maintenance. """
    reservation = get_test_reservation(
        rental=self.rental, check_in=str_to_tz_dt('2018-12-24 16:00'),
        check_out=str_to_tz_dt('2018-12-27 11:00'))

    post_sync.send(sender=Reservation, instance=reservation)

    self.maintenance.refresh_from_db()
    self.assertTrue(self.maintenance.canceled_at)
    self.assertEqual(
        'A guest booked a stay before this job was accepted',
        self.maintenance.permanently_canceled_reason)
