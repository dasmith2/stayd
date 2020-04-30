from datetime import date
from unittest.mock import Mock, call

from errors.models import ErrorLogger
from rentals.models import UNAVAILABLE, AVAILABLE
from rentals.tests import get_test_rental, get_test_building
from reservations.models import Reservation
from reservations.tests import get_test_reservation
from work.api import API
from work.api_examples import CREATE_JOB
from work.models.maintenance import Maintenance
from work.models.message import (
    MessageSender, Message, DELAYED_TICKET, HIGH_PRIORITY_TICKET_JOB_CANCELED)
from work.models.raw_event import RawEvent
from work.models.sla import (
    NOW, URGENT, NEXT_CHECKOUT, NEXT_VISIT, NEXT_VACANT_NIGHT, DONT_SCHEDULE)
from work.models.ticket import Ticket
from work.models.ticket_scheduler import (
    schedule, double_check_blocks_background,
    get_upcoming_unaccepted_maintenances, compatible,
    added_to_which_maintenance, unscheduled_tickets, ticket_post_save,
    maintenance_post_save_alert_incomplete)
from work.models.work import FLEXIBLE, CANCELED, CREATED
from work.tests.test_maintenance_checklist import (
    get_test_maintenance_checklist)
from work.tests.test_maintenance import get_test_maintenance
from work.tests.test_rental import get_test_properly_rental
from work.tests.test_ticket import get_test_ticket
from work.tests.test_work_type import get_test_work_type
from work.tests.test_worker import get_test_independent_worker
from util.signals import post_sync
from util.tests import TestCase
from util.timezone import str_to_tz_dt


class AlertIncompleteTests(TestCase):
  def test_alert_incomplete_ticket(self):
    message_sender = Mock(spec=MessageSender)
    maintenance = get_test_maintenance(
        offered_start_time=str_to_tz_dt('2018-12-25 11:15'),
        completed_at=str_to_tz_dt('2018-12-25 15:45'))
    rental = get_test_rental(alerts_email='alert@building.com')
    get_test_ticket(maintenance=maintenance, rental=rental)

    for i in range(2):
      maintenance_post_save_alert_incomplete(
          Maintenance, maintenance, message_sender=message_sender)

    message = Message.objects.get(
        reason=DELAYED_TICKET, work=maintenance, to='alert@building.com')
    self.assertEqual([call(message)], message_sender.send.call_args_list)


class GetStuffTests(TestCase):
  def test_get_upcoming_unaccepted_maintenances(self):
    get_test_maintenance(
        accepted_by=get_test_independent_worker(), job_request_id='a',
        offered_start_time=str_to_tz_dt('2018-12-02'))
    unaccepted = get_test_maintenance(
        accepted_by=None, job_request_id='b',
        offered_start_time=str_to_tz_dt('2018-12-02'))
    self.assertEqual(
        [unaccepted], list(get_upcoming_unaccepted_maintenances(
            nnow=str_to_tz_dt('2018-12-01'))))

  def test_unscheduled_tickets(self):
    should = get_test_ticket(title='should')
    should_2 = get_test_ticket(
        title='should 2', maintenance=get_test_maintenance(
            canceled_at=str_to_tz_dt('2018-12-01'),
            offered_start_time=str_to_tz_dt('2018-12-03 11:15')))
    get_test_ticket(title='shouldnt 1', maintenance=get_test_maintenance(
        offered_start_time=str_to_tz_dt('2018-12-03 11:15')))
    get_test_ticket(
        title='shouldnt 2', completed_at=str_to_tz_dt('2018-12-03 11:15'))
    self.assertEqual([should, should_2], list(unscheduled_tickets()))


class PutTicketInMaintenanceTests(TestCase):
  def test_compatible(self):
    rental = get_test_rental()
    work_type = get_test_work_type()
    # SLAs
    self.assertTrue(compatible(
        get_test_ticket(rental=rental, sla=NOW, work_type=work_type),
        get_test_ticket(rental=rental, sla=URGENT, work_type=work_type)))
    self.assertFalse(compatible(
        get_test_ticket(rental=rental, sla=NOW, work_type=work_type),
        get_test_ticket(
            rental=rental, sla=NEXT_CHECKOUT, work_type=work_type)))
    self.assertTrue(compatible(
        get_test_ticket(rental=rental, sla=NEXT_CHECKOUT, work_type=work_type),
        get_test_ticket(rental=rental, sla=NEXT_VISIT, work_type=work_type)))
    # Rental
    self.assertFalse(compatible(
        get_test_ticket(rental=rental, sla=NOW, work_type=work_type),
        get_test_ticket(
            rental=get_test_rental(), sla=URGENT, work_type=work_type)))
    # Who will do the work
    t1 = get_test_ticket(rental=rental, sla=NOW, work_type=work_type)
    t2 = get_test_ticket(
        rental=rental, sla=URGENT, work_type=get_test_work_type(name='what?'))
    self.assertFalse(compatible(t1, t2))

  def test_added_to_which_maintenance(self):
    rental = get_test_rental()
    maintenance = get_test_maintenance(
        offered_start_time=str_to_tz_dt('2018-12-25 11:15'))
    worker = get_test_independent_worker(buildings=[rental.building])
    work_type = get_test_work_type()
    get_test_ticket(
        rental=rental, sla=NOW, offered_to=[worker],
        maintenance=maintenance, work_type=work_type)
    yes_ticket = get_test_ticket(
        rental=rental, sla=URGENT, offered_to=[worker],
        work_type=work_type)
    self.assertEqual(maintenance, added_to_which_maintenance(
        yes_ticket, [maintenance]))
    no_ticket = get_test_ticket(
        rental=rental, sla=URGENT, offered_to=[get_test_independent_worker()],
        work_type=work_type)
    self.assertIsNone(added_to_which_maintenance(no_ticket, [maintenance]))


class ScheduleBySLATests(TestCase):
  """ Here, I don't care about things that stop a ticket from being scheduled.
  I'm just trying to make sure that when tickets do get scheduled they do so at
  the right time considering their SLA. """
  def setUp(self):
    super().setUp()
    building = get_test_building(alerts_email='building@email.com')
    self.rental = get_test_properly_rental(building=building).rental
    self.work_type = get_test_work_type()
    self.worker = get_test_independent_worker(
        buildings=[self.rental.building], work_types=[self.work_type])
    self.checklist = get_test_maintenance_checklist(checklist_id='whatever')
    get_test_reservation(
        rental=self.rental, check_in=str_to_tz_dt('2018-12-20 16:00'),
        check_out=str_to_tz_dt('2018-12-31 11:00'))

  def test_manual_start_time(self):
    manual_start_time_1 = get_test_ticket(
        manual_start_time=str_to_tz_dt('2018-12-26 12:00'),
        created_at=str_to_tz_dt('2018-12-25 12:00'), rental=self.rental,
        work_type=self.work_type, checklist=self.checklist)
    manual_start_time_2 = get_test_ticket(
        manual_start_time=str_to_tz_dt('2018-12-26 12:00'),
        created_at=str_to_tz_dt('2018-12-25 12:05'), rental=self.rental,
        work_type=self.work_type, checklist=self.checklist)
    # Different start time, lt 10 minutes, should never get scheduled in this
    # test.
    get_test_ticket(
        manual_start_time=str_to_tz_dt('2018-12-26 13:00'),
        created_at=str_to_tz_dt('2018-12-25 12:03'), rental=self.rental,
        work_type=self.work_type, checklist=self.checklist)

    # Waits 10 minutes
    schedule(nnow=str_to_tz_dt('2018-12-25 12:05'))
    self.assertFalse(Maintenance.objects.exists())
    schedule(nnow=str_to_tz_dt('2018-12-25 12:10'))
    self.assertTrue(Maintenance.objects.exists())

    maintenance = Maintenance.objects.first()
    self.assertEqual(
        set([manual_start_time_1, manual_start_time_2]),
        set(maintenance.ticket_set.all()))
    self.assertEqual(
        str_to_tz_dt('2018-12-26 12:00'), maintenance.offered_start_time)

  def test_all_dont_fix_or_complete_cancels_job(self):
    maintenance = get_test_maintenance(
        job_request_id='bytheskinofmyteeth',
        offered_start_time=str_to_tz_dt('2018-12-31 11:15'))
    rental = get_test_rental()
    ticket_1 = get_test_ticket(
        maintenance=maintenance, sla=NEXT_VISIT, rental=rental)
    ticket_2 = get_test_ticket(
        maintenance=maintenance, sla=NEXT_VISIT, rental=rental)

    ticket_1.sla = DONT_SCHEDULE
    ticket_1.save()
    ticket_post_save(
        Ticket, ticket_1, ok_to_run_in_tests=True,
        nnow=str_to_tz_dt('2018-12-28 15:00'))
    maintenance.refresh_from_db()
    self.assertIsNone(maintenance.canceled_at)

    # Now that all the tickets in this job are DONT_SCHEDULE, cancel the job.
    ticket_2.completed_at = str_to_tz_dt('2018-12-28 15:30')
    ticket_2.save()
    ticket_post_save(
        Ticket, ticket_2, ok_to_run_in_tests=True,
        nnow=str_to_tz_dt('2018-12-28 15:05'))
    maintenance.refresh_from_db()
    self.assertTrue(maintenance.canceled_at)

  def test_emergency_schedules_immediately_includes_urgent(self):  # 1
    urgent = get_test_ticket(
        sla=URGENT, created_at=str_to_tz_dt('2018-12-25 12:00'),
        rental=self.rental, work_type=self.work_type, checklist=self.checklist)
    next_visit = get_test_ticket(
        sla=NEXT_VISIT, created_at=str_to_tz_dt('2018-12-25 12:24'),
        rental=self.rental, work_type=self.work_type, checklist=self.checklist)
    emergency = get_test_ticket(
        sla=NOW, created_at=str_to_tz_dt('2018-12-25 12:24'),
        rental=self.rental, work_type=self.work_type, checklist=self.checklist)

    # I COULD call schedule here, but we want NOW to schedule immediately
    # which I accomplish through a post_save receiver.
    ticket_post_save(
        Ticket, emergency, ok_to_run_in_tests=True,
        nnow=str_to_tz_dt('2018-12-25 12:25'))

    # It's a bad idea to do non-emergency maintenance. a) there could be a
    # guest in the apartment, which we COULD program around, but also b) we
    # don't want to add noise to an intense situation. What if a low priority
    # ticket says to stop off and pick up touch up paint but the apartment is
    # flooding. Forget the paint, fix the emergency!
    next_visit.refresh_from_db()
    self.assertIsNone(next_visit.maintenance)

    urgent.refresh_from_db()
    emergency.refresh_from_db()
    self.assertIsNone(urgent.not_scheduled_reason)
    self.assertIsNone(emergency.not_scheduled_reason)
    self.assertEqual(urgent.maintenance, emergency.maintenance)
    self.assertEqual(FLEXIBLE, urgent.maintenance.fixed_or_flexible)
    # I scheduled for 5 minutes from now because Properly would freak out if
    # you schedule in the past. It makes sense though and you can always just
    # start 5 minutes early so I'll leave it that way.
    self.assertEqual(
        str_to_tz_dt('2018-12-25 12:30'),
        urgent.maintenance.offered_start_time)
    self.assertEqual(
        str_to_tz_dt('2018-12-25 16:30'), urgent.maintenance.deadline)

  def test_urgent_schedules_in_half_an_hour(self):  # 2
    urgent = get_test_ticket(
        sla=URGENT, created_at=str_to_tz_dt('2018-12-25 12:00'),
        work_type=self.work_type, checklist=self.checklist, rental=self.rental)

    schedule(nnow=str_to_tz_dt('2018-12-25 12:29'))
    self.assertFalse(Maintenance.objects.exists())

    schedule(nnow=str_to_tz_dt('2018-12-25 12:30'))
    urgent.refresh_from_db()
    self.assertIsNone(urgent.not_scheduled_reason)
    self.assertEqual(FLEXIBLE, urgent.maintenance.fixed_or_flexible)
    self.assertEqual(
        str_to_tz_dt('2018-12-25 12:35'),
        urgent.maintenance.offered_start_time)
    self.assertEqual(
        str_to_tz_dt('2018-12-26 12:35'), urgent.maintenance.deadline)

  def test_canceled_non_urgent_job_schedules_just_like_no_job(self):  # 3
    """ When we move off Properly, non-urgent jobs wont alert or require
    service providers to decline if they don't want the job. Accepting and
    starting will happen at the exact same time, as opposed to with Properly
    where accepting happened well before starting. This is how we can auto
    reschedule non-urgent tickets without fear of infinite cancel re-offer
    loops like we used to have to program around with Properly. """
    canceled = get_test_maintenance(
        offered_start_time=str_to_tz_dt('2018-12-25 12:15'),
        canceled_at=str_to_tz_dt('2018-12-25 12:15'),
        job_request_id='priests_with_guns')
    next_checkout = get_test_ticket(
        sla=NEXT_CHECKOUT, created_at=str_to_tz_dt('2018-12-25'),
        rental=self.rental, work_type=self.work_type, checklist=self.checklist)

    schedule(nnow=str_to_tz_dt('2018-12-28 11:15'))
    next_checkout.refresh_from_db()
    self.assertIsNone(next_checkout.not_scheduled_reason)
    self.assertNotEqual(canceled, next_checkout.maintenance)
    self.assertEqual(CREATED, next_checkout.maintenance.status())

  def test_canceled_urgent_job_alerts_does_not_reschedule(self):  # 3.5
    """ Urgent jobs, however, will retain the accept step. So the way we avoid
    an infinite cancel re-offer loop is to NOT auto reschedule these, and
    instead send an alert. """
    going_to_cancel = get_test_maintenance(
        offered_start_time=str_to_tz_dt('2018-12-25 12:15'),
        job_request_id='priests_with_guns')
    urgent = get_test_ticket(
        sla=URGENT, created_at=str_to_tz_dt('2018-12-25'),
        rental=self.rental, work_type=self.work_type, checklist=self.checklist,
        maintenance=going_to_cancel)
    message_sender = Mock(spec=MessageSender)

    # I've accidentally programmed things to re-cancel before and this caused
    # the message to go out a bunch of times.
    for i in range(2):
      going_to_cancel.was_canceled(
          'Things went south!', message_sender=message_sender)

    message = Message.objects.get(
        reason=HIGH_PRIORITY_TICKET_JOB_CANCELED, to='building@email.com')
    self.assertEqual([call(message)], message_sender.send.call_args_list)

    schedule(nnow=str_to_tz_dt('2018-12-28 11:15'))
    urgent.refresh_from_db()
    self.assertEqual(going_to_cancel, urgent.maintenance)
    self.assertEqual(CANCELED, urgent.maintenance.status())

  def test_unaccepted_maintenance_recreates(self):  # 4
    offered = get_test_maintenance(
        offered_start_time=str_to_tz_dt('2018-12-31 11:15'),
        deadline=str_to_tz_dt('2018-12-31 15:45'),
        job_request_id='priests_with_guns', offered_to=[self.worker])
    already_scheduled = get_test_ticket(
        sla=NEXT_CHECKOUT, created_at=str_to_tz_dt('2018-12-29 12:00'),
        maintenance=offered, offered_to=[self.worker], rental=self.rental,
        checklist=self.checklist)
    not_yet_scheduled = get_test_ticket(
        sla=NEXT_VISIT, created_at=str_to_tz_dt('2018-12-29 12:05'),
        offered_to=[self.worker], rental=self.rental,
        checklist=self.checklist)

    schedule(nnow=str_to_tz_dt('2018-12-29 12:10'))
    offered.refresh_from_db()
    already_scheduled.refresh_from_db()
    not_yet_scheduled.refresh_from_db()

    self.assertIsNone(not_yet_scheduled.not_scheduled_reason)
    self.assertEqual(
        set([already_scheduled, not_yet_scheduled]),
        set(offered.ticket_set.all()))
    self.assertEqual(1, offered.offered_to.count())
    self.assertEqual(
        self.worker, offered.offered_to.first().get_child_class_instance())

  def test_accepted_maintenance_left_alone(self):  # 5
    """ This limitation is entirely due to Properly and my reluctance to
    program up a thing where I cancel an accepted job and reoffer it only to
    the worker who accepted it with new tasks. What if they don't accept the
    new job? Even more likely, every properly api call and webhook has a, like,
    20% chance of failing, and this would require a cancel call, a create call,
    and an accepted webhook.

    If we can get a reliable worker communication channel for maintenance, one
    that allows modification of tasks post-acceptance, then this will change.
    """
    offered = get_test_maintenance(
        offered_start_time=str_to_tz_dt('2018-12-25 12:15'),
        canceled_at=str_to_tz_dt('2018-12-25 12:15'),
        job_request_id='priests_with_guns',
        offered_to=[self.worker], accepted_by=self.worker,
        accepted_at=str_to_tz_dt('2018-12-25 12:00'))
    get_test_ticket(
        sla=URGENT, created_at=str_to_tz_dt('2018-12-25 11:45'),
        maintenance=offered, offered_to=[self.worker], rental=self.rental,
        work_type=self.work_type, checklist=self.checklist)
    get_test_ticket(
        sla=URGENT, created_at=str_to_tz_dt('2018-12-25 12:05'),
        offered_to=[self.worker], rental=self.rental, work_type=self.work_type,
        checklist=self.checklist)

    self.assertEqual(1, Maintenance.objects.count())
    schedule(nnow=str_to_tz_dt('2018-12-25 12:10'))
    self.assertEqual(1, Maintenance.objects.count())

  def test_next_checkout_waits_until_3_days_before_checkout(self):  # 6
    next_checkout = get_test_ticket(
        sla=NEXT_CHECKOUT, created_at=str_to_tz_dt('2018-12-25'),
        rental=self.rental, work_type=self.work_type, checklist=self.checklist)

    schedule(nnow=str_to_tz_dt('2018-12-28 11:14'))
    self.assertFalse(Maintenance.objects.exists())
    schedule(nnow=str_to_tz_dt('2018-12-28 11:15'))
    next_checkout.refresh_from_db()
    self.assertIsNone(next_checkout.not_scheduled_reason)
    self.assertTrue(Maintenance.objects.exists())

    next_checkout.refresh_from_db()
    self.assertEqual(FLEXIBLE, next_checkout.maintenance.fixed_or_flexible)
    self.assertEqual(
        str_to_tz_dt('2018-12-31 11:15'),
        next_checkout.maintenance.offered_start_time)
    self.assertEqual(
        str_to_tz_dt('2018-12-31 15:45'),
        next_checkout.maintenance.deadline)

  def test_next_checkout_includes_next_visit(self):  # 7
    next_checkout = get_test_ticket(
        sla=NEXT_CHECKOUT, created_at=str_to_tz_dt('2018-12-25'),
        rental=self.rental, work_type=self.work_type, checklist=self.checklist)
    next_visit = get_test_ticket(
        sla=NEXT_VISIT, created_at=str_to_tz_dt('2018-12-25'),
        rental=self.rental, work_type=self.work_type, checklist=self.checklist)
    get_test_ticket(  # Dont schedule obviously
        sla=DONT_SCHEDULE, created_at=str_to_tz_dt('2018-12-25'),
        rental=self.rental, work_type=self.work_type, checklist=self.checklist)

    schedule(nnow=str_to_tz_dt('2018-12-28 11:00'))

    next_checkout.refresh_from_db()
    next_visit.refresh_from_db()
    self.assertEqual(next_checkout.maintenance, next_visit.maintenance)

  def test_next_visit_alone_doesnt_schedule(self):  # 8
    get_test_ticket(
        sla=NEXT_VISIT, created_at=str_to_tz_dt('2018-12-25'),
        rental=self.rental, work_type=self.work_type, checklist=self.checklist)

    schedule(nnow=str_to_tz_dt('2018-12-28 11:00'))
    self.assertFalse(Maintenance.objects.exists())

  def test_next_checkout_lt_3_hours_schedules_immediately(self):  # 9
    ticket = get_test_ticket(
        sla=NEXT_CHECKOUT, created_at=str_to_tz_dt('2018-12-31 09:00'),
        rental=self.rental, work_type=self.work_type, checklist=self.checklist)

    schedule(nnow=str_to_tz_dt('2018-12-31 09:00'))
    ticket.refresh_from_db()
    self.assertIsNone(ticket.not_scheduled_reason)
    self.assertTrue(Maintenance.objects.exists())

  def test_next_checkout_waits_12_hours(self):  # 10
    ticket = get_test_ticket(
        sla=NEXT_CHECKOUT, created_at=str_to_tz_dt('2018-12-29 12:00'),
        rental=self.rental, work_type=self.work_type, checklist=self.checklist)

    schedule(nnow=str_to_tz_dt('2018-12-29 23:59'))
    self.assertFalse(Maintenance.objects.exists())
    schedule(nnow=str_to_tz_dt('2018-12-30 00:00'))
    ticket.refresh_from_db()
    self.assertIsNone(ticket.not_scheduled_reason)
    self.assertTrue(Maintenance.objects.exists())

  def test_next_checkout_waits_until_3_hours_before_checkout(self):  # 11
    ticket = get_test_ticket(
        sla=NEXT_CHECKOUT, created_at=str_to_tz_dt('2018-12-31 05:00'),
        rental=self.rental, work_type=self.work_type, checklist=self.checklist)

    schedule(nnow=str_to_tz_dt('2018-12-31 08:14'))
    self.assertFalse(Maintenance.objects.exists())
    schedule(nnow=str_to_tz_dt('2018-12-31 08:15'))
    ticket.refresh_from_db()
    self.assertIsNone(ticket.not_scheduled_reason)
    self.assertTrue(Maintenance.objects.exists())


class WhenCantScheduleTests(TestCase):
  def setUp(self):
    super().setUp()
    self.building = get_test_building(nickname='Daves Diner')
    self.rental = get_test_rental(building=self.building)
    self.properly_rental = get_test_properly_rental(rental=self.rental)
    self.work_type = get_test_work_type(name='Eating')
    self.worker = get_test_independent_worker(
        buildings=[self.building], work_types=[self.work_type],
        name='Mrs. Messy')
    self.checklist = get_test_maintenance_checklist(checklist_id='whatever')

  def test_timing_issues(self):
    get_test_reservation(
        rental=self.rental, check_in=str_to_tz_dt('2018-12-25 16:00'),
        check_out=str_to_tz_dt('2018-12-26 11:00'))
    ticket = get_test_ticket(
        sla=URGENT, rental=self.rental, work_type=self.work_type,
        checklist=self.checklist,
        created_at=str_to_tz_dt('2018-12-25 11:30'))

    schedule(nnow=str_to_tz_dt('2018-12-25 11:59'))
    ticket.refresh_from_db()
    self.assertEqual(
        'URGENT tickets wait 30 minutes before creating a job',
        ticket.not_scheduled_reason.name)

    ticket.sla = ''
    ticket.manual_start_time = str_to_tz_dt('2018-12-26 12:00')
    ticket.save()
    nnow = str_to_tz_dt('2018-12-25 11:39')
    schedule(nnow=nnow)
    ticket.refresh_from_db()
    self.assertEqual((
        'Tickets with manual start times wait 10 minutes to '
        'schedule'), ticket.not_scheduled_reason.name)

    ticket.sla = NEXT_CHECKOUT
    ticket.manual_start_time = None
    ticket.save()
    schedule(nnow=str_to_tz_dt('2018-12-25 23:29'))
    ticket.refresh_from_db()
    self.assertEqual((
        'Next checkout tickets wait 12 hours, or until 3 hours before the '
        'next usable time before creating a '
        'job'), ticket.not_scheduled_reason.name)

    schedule(nnow=str_to_tz_dt('2018-12-27 23:30'))
    ticket.refresh_from_db()
    self.assertEqual(
        'There aren\'t any check ins or outs in the next 3 days',
        ticket.not_scheduled_reason.name)

  def test_worker_issues(self):
    self.worker.work_types.set([])
    ticket = get_test_ticket(
        sla=NOW, rental=self.rental, work_type=self.work_type,
        checklist=self.checklist,
        created_at=str_to_tz_dt('2018-12-25 12:00'))

    schedule(nnow=str_to_tz_dt('2018-12-25 12:00'))
    ticket.refresh_from_db()
    self.assertEqual((
        'There are no workers of this type configured for this '
        'building'), ticket.not_scheduled_reason.name)

    ticket.work_type = None
    ticket.offered_to.set([get_test_independent_worker(name='Mr. Moss')])
    ticket.save()
    schedule(nnow=str_to_tz_dt('2018-12-25 12:00'))
    ticket.refresh_from_db()
    self.assertEqual((
        'None of the workers configured for this ticket are '
        'configured for this building'), ticket.not_scheduled_reason.name)

    # While we're here, make sure offered_to does work when it's correct.
    ticket.offered_to.set([self.worker])
    ticket.save()
    api = Mock(spec=API)
    api.job_request_create.return_value = CREATE_JOB
    schedule(nnow=str_to_tz_dt('2018-12-25 12:00'), api=api)
    ticket.refresh_from_db()
    self.assertIsNone(ticket.not_scheduled_reason)
    self.assertEqual(1, ticket.maintenance.offered_to.count())
    self.assertEqual(
        self.worker,
        ticket.maintenance.offered_to.first().get_child_class_instance())

  def test_nothing_compatible(self):
    ticket = get_test_ticket(
        sla=NEXT_VISIT, rental=self.rental, work_type=self.work_type,
        checklist=self.checklist,
        created_at=str_to_tz_dt('2018-12-25 12:00'))
    schedule(nnow=str_to_tz_dt('2018-12-26 12:00'))
    ticket.refresh_from_db()
    self.assertEqual((
        'There aren\'t any unaccepted, upcoming Maintenance jobs with an '
        'appropriate SLA for this rental that I can attach this '
        'to'), ticket.not_scheduled_reason.name)

  def test_no_context_reasons(self):
    rental = get_test_rental(nickname='Daves cave')
    ticket = get_test_ticket(
        created_at=str_to_tz_dt('2018-12-01 12:00'),
        not_our_responsibility='Not my fault y\'all!', rental=rental)
    schedule(nnow=str_to_tz_dt('2018-12-01 13:00'))
    ticket.refresh_from_db()
    self.assertEqual(
        'It\'s not our responsibility to resolve this ticket',
        ticket.not_scheduled_reason.name)

    ticket.not_our_responsibility = ''
    ticket.save()
    schedule(nnow=str_to_tz_dt('2018-12-01 13:00'))
    ticket.refresh_from_db()
    self.assertEqual(
        'This ticket doesn\'t have an SLA or manual start time',
        ticket.not_scheduled_reason.name)

    ticket.sla = DONT_SCHEDULE
    ticket.save()
    schedule(nnow=str_to_tz_dt('2018-12-01 13:00'))
    ticket.refresh_from_db()
    self.assertEqual(
        'No need to schedule a ticket we won\'t fix.',
        ticket.not_scheduled_reason.name)

    ticket.sla = NOW
    ticket.save()
    schedule(nnow=str_to_tz_dt('2018-12-01 13:00'))
    ticket.refresh_from_db()
    self.assertEqual(
        'You must specify precisely 1 of work_type and offered_to',
        ticket.not_scheduled_reason.name)

    ticket.work_type = get_test_work_type()
    ticket.save()
    schedule(nnow=str_to_tz_dt('2018-12-01 13:00'))
    ticket.refresh_from_db()
    self.assertEqual(
        'You must set either the checklist or the existing_checklist_url',
        ticket.not_scheduled_reason.name)

    ticket.existing_checklist_url = 'whatever.com:/hhtp://'
    ticket.save()
    schedule(nnow=str_to_tz_dt('2018-12-01 13:00'))
    ticket.refresh_from_db()
    self.assertEqual(
        'The existing checklist url is invalid',
        ticket.not_scheduled_reason.name)

    ticket.existing_checklist_url = (
        'https://app.getproperly.com/#/checklists/vysjlbB73W/iQb2SQqIJF/')
    ticket.save()
    schedule(nnow=str_to_tz_dt('2018-12-01 13:00'))
    ticket.refresh_from_db()
    self.assertEqual(
        'This rental isn\'t configured with a Properly Rental',
        ticket.not_scheduled_reason.name)

    get_test_properly_rental(rental=rental, properly_property_id=None)
    schedule(nnow=str_to_tz_dt('2018-12-01 13:00'))
    ticket.refresh_from_db()
    self.assertEqual(
        'This rental\'s Properly Rental ID isn\'t set',
        ticket.not_scheduled_reason.name)


class VacantNightTests(TestCase):
  """ Vacant night is complicated enough it gets its own set of tests. """
  def setUp(self):
    super().setUp()
    self.rental = get_test_properly_rental(guesty_id='whatever_gid').rental
    self.scheduling_api = Mock()
    self.work_type = get_test_work_type()
    self.worker = get_test_independent_worker(
        buildings=[self.rental.building], work_types=[self.work_type],
        worker_id='indep_worker_id', email='indep@worker.email')
    # 2018-12-09 is valid because it's a Sunday before a reservation.
    get_test_reservation(
        rental=self.rental, check_in=str_to_tz_dt('2018-12-10 16:00'),
        check_out=str_to_tz_dt('2018-12-20 11:00'))
    # 2018-12-20 is not a valid Thursday because it has a reservation that
    # night.
    get_test_reservation(
        rental=self.rental, check_in=str_to_tz_dt('2018-12-20 16:00'),
        check_out=str_to_tz_dt('2018-12-23 11:00'))
    # 2018-12-23 is valid because it's a Sunday before and after a reservation.
    # 2018-12-28 would be valid because it's after a reservation, except that
    # it's a Friday.
    get_test_reservation(
        rental=self.rental, check_in=str_to_tz_dt('2018-12-24 16:00'),
        check_out=str_to_tz_dt('2018-12-28 11:00'))
    # 2018-12-30 is valid because it's after a reservation.
    get_test_reservation(
        rental=self.rental, check_in=str_to_tz_dt('2018-12-29 16:00'),
        check_out=str_to_tz_dt('2018-12-30 11:00'))

    self.next_vacant = get_test_ticket(
        sla=NEXT_VACANT_NIGHT, work_type=self.work_type, rental=self.rental,
        checklist=get_test_maintenance_checklist(checklist_id='do_stuff'),
        created_at=str_to_tz_dt('2018-12-01'))
    # Throw a second one in the mix, make sure we don't double up stuff we
    # aren't supposed to.
    get_test_ticket(
        sla=NEXT_VACANT_NIGHT, work_type=self.work_type, rental=self.rental,
        checklist=get_test_maintenance_checklist(checklist_id='do_stuff'),
        created_at=str_to_tz_dt('2018-12-01'))

  def test_10am_counts_as_after_a_reservation_when_vacant_night(  # 1
      self):
    schedule(  # The 3rd is a Monday
        nnow=str_to_tz_dt('2018-12-03 10:00'), next_checkout_days_in_advance=3)
    self.next_vacant.refresh_from_db()
    self.assertIsNone(self.next_vacant.not_scheduled_reason)
    self.assertEqual(1, Maintenance.objects.count())

  def test_vacancy_tests_irrelevant_for_maintenance_only_unit(self):
    self.rental.maintenance_purposes_only = True
    self.rental.save()
    # See test_when_cant_you_schedule where 2018-12-01 12:00 gets blocked due
    # to vacancy considerations.
    schedule(
        nnow=str_to_tz_dt('2018-12-01 12:00'), next_checkout_days_in_advance=3)
    self.next_vacant.refresh_from_db()
    self.assertIsNone(self.next_vacant.not_scheduled_reason)
    self.assertEqual(1, Maintenance.objects.count())

  def test_when_cant_you_schedule(self):  # 2
    # Can't schedule in the middle of nowhere, because that might split up a
    # big valuable reservation. There must be a reservation immediately before
    # or after or preferably before AND after the vacant night. If this were
    # called at 10am it would be a different story because between midnight and
    # 11am, the upcoming 11am counts as immediately after a reservation.
    schedule(
        nnow=str_to_tz_dt('2018-12-01 12:00'), next_checkout_days_in_advance=3)
    self.next_vacant.refresh_from_db()
    self.assertEqual((
        'There aren\'t any non-weekend vacant nights before or after a '
        'reservation'), self.next_vacant.not_scheduled_reason.name)

    # Can't schedule in the middle of a reservation
    schedule(
        nnow=str_to_tz_dt('2018-12-10 12:00'), next_checkout_days_in_advance=3)
    self.next_vacant.refresh_from_db()
    self.assertEqual(
        'The next 3 days are taken up by a single reservation',
        self.next_vacant.not_scheduled_reason.name)

    # Can't schedule between reservations without an open night
    schedule(
        nnow=str_to_tz_dt('2018-12-18 12:00'), next_checkout_days_in_advance=3)
    self.next_vacant.refresh_from_db()
    self.assertEqual(
        'There are no vacant nights in the next 3 days',
        self.next_vacant.not_scheduled_reason.name)

    # The 28th is a Friday. Can't schedule on a weekend.
    schedule(
        nnow=str_to_tz_dt('2018-12-25 12:00'), next_checkout_days_in_advance=3)
    self.next_vacant.refresh_from_db()
    self.assertEqual((
        'The only vacant nights are on weekends which are too valuable to '
        'block for maintenance'), self.next_vacant.not_scheduled_reason.name)

    self.assertFalse(Maintenance.objects.exists())

  def test_before_a_reservation(self):  # 3
    schedule(
        nnow=str_to_tz_dt('2018-12-07 12:00'), next_checkout_days_in_advance=3)
    self.next_vacant.refresh_from_db()
    self.assertIsNone(self.next_vacant.not_scheduled_reason)
    self.assertEqual(
        str_to_tz_dt('2018-12-09 11:15'),
        self.next_vacant.maintenance.offered_start_time)

  def test_before_and_after_a_reservation(self):  # 4
    schedule(
        nnow=str_to_tz_dt('2018-12-20 12:00'), next_checkout_days_in_advance=3)
    self.next_vacant.refresh_from_db()
    self.assertIsNone(self.next_vacant.not_scheduled_reason)
    self.assertEqual(
        str_to_tz_dt('2018-12-23 11:15'),
        self.next_vacant.maintenance.offered_start_time)

  def test_after_a_reservation(self):  # 5
    schedule(
        nnow=str_to_tz_dt('2018-12-27 12:00'), next_checkout_days_in_advance=3)
    self.next_vacant.refresh_from_db()
    self.assertEqual(
        str_to_tz_dt('2018-12-30 11:15'),
        self.next_vacant.maintenance.offered_start_time)

  def test_vacant_night_offered_booked_canceled(self):  # 6
    schedule(  # Will book on the 23rd
        nnow=str_to_tz_dt('2018-12-20 12:00'), next_checkout_days_in_advance=3)
    self.next_vacant.refresh_from_db()
    self.assertIsNone(self.next_vacant.not_scheduled_reason)
    self.assertEqual(1, Maintenance.objects.count())
    maintenance = Maintenance.objects.first()
    self.assertNotEqual(CANCELED, maintenance.status())

    reservation = get_test_reservation(
        rental=self.rental, check_in=str_to_tz_dt('2018-12-20 16:00'),
        check_out=str_to_tz_dt('2018-12-24 11:00'))
    post_sync.send(sender=Reservation, instance=reservation)
    maintenance.refresh_from_db()

    self.assertEqual(CANCELED, maintenance.status())
    self.assertEqual(
        'A guest booked a stay before this job was accepted',
        maintenance.permanently_canceled_reason)

  def test_vacant_night_accepted_blocked_canceled_unblocked(self):  # 7
    schedule(  # Will book on the 23rd
        nnow=str_to_tz_dt('2018-12-20 12:00'), next_checkout_days_in_advance=3)
    self.next_vacant.refresh_from_db()
    self.assertIsNone(self.next_vacant.not_scheduled_reason)
    maintenance = Maintenance.objects.first()
    scheduling_api = Mock()

    RawEvent().handle_accepted_job_request(
        maintenance, 'indep@worker.email', None, None, scheduling_api)
    block = call(
        'whatever_gid', date(2018, 12, 23),
        'Vacant night required for maintenance')
    self.assertEqual([block], scheduling_api.block.call_args_list)

    maintenance.cancel(
        'Whatever random reason.', scheduling_api=scheduling_api)
    unblock = call('whatever_gid', date(2018, 12, 23))
    self.assertEqual([unblock], scheduling_api.unblock.call_args_list)

  def test_double_check_successful_block(self):  # 8
    maintenance = get_test_maintenance(
        job_request_id='whatever',
        offered_start_time=str_to_tz_dt('2018-12-23 11:15'),
        accepted_by=self.worker)
    self.next_vacant.maintenance = maintenance
    self.next_vacant.save()

    error_logger = Mock(spec=ErrorLogger)
    self.scheduling_api.get_calendar.return_value = [{'status': UNAVAILABLE}]

    double_check_blocks_background(
        nnow=str_to_tz_dt('2018-12-20 12:00'),
        scheduling_api=self.scheduling_api, error_logger=error_logger)

    self.assertEqual(
        [call('whatever_gid', date(2018, 12, 23), date(2018, 12, 23))],
        self.scheduling_api.get_calendar.call_args_list)
    self.assertEqual(0, len(error_logger.log_error.call_args_list))

  def test_double_check_failed_block(self):  # 9
    maintenance = get_test_maintenance(
        job_request_id='whatever',
        offered_start_time=str_to_tz_dt('2018-12-23 11:15'),
        accepted_by=self.worker)
    self.next_vacant.maintenance = maintenance
    self.next_vacant.save()

    error_logger = Mock(spec=ErrorLogger)
    self.scheduling_api.get_calendar.return_value = [{'status': AVAILABLE}]

    double_check_blocks_background(
        nnow=str_to_tz_dt('2018-12-20 12:00'),
        scheduling_api=self.scheduling_api, error_logger=error_logger)

    self.assertEqual(1, len(error_logger.log_error.call_args_list))

  def test_double_check_successful_unblock(self):  # 10
    maintenance = get_test_maintenance(
        job_request_id='whatever',
        offered_start_time=str_to_tz_dt('2018-12-23 11:15'),
        accepted_by=self.worker, canceled_at=str_to_tz_dt('2018-12-20 12:00'))
    self.next_vacant.maintenance = maintenance
    self.next_vacant.save()

    error_logger = Mock(spec=ErrorLogger)
    self.scheduling_api.get_calendar.return_value = [{'status': AVAILABLE}]

    double_check_blocks_background(
        nnow=str_to_tz_dt('2018-12-20 12:00'),
        scheduling_api=self.scheduling_api, error_logger=error_logger)

    self.assertEqual(0, len(error_logger.log_error.call_args_list))

  def test_double_check_failed_unblock(self):  # 11
    maintenance = get_test_maintenance(
        job_request_id='whatever',
        offered_start_time=str_to_tz_dt('2018-12-23 11:15'),
        accepted_by=self.worker, canceled_at=str_to_tz_dt('2018-12-20 12:00'))
    self.next_vacant.maintenance = maintenance
    self.next_vacant.save()

    error_logger = Mock(spec=ErrorLogger)
    self.scheduling_api.get_calendar.return_value = [{'status': UNAVAILABLE}]

    double_check_blocks_background(
        nnow=str_to_tz_dt('2018-12-20 12:00'),
        scheduling_api=self.scheduling_api, error_logger=error_logger)

    self.assertEqual(1, len(error_logger.log_error.call_args_list))
