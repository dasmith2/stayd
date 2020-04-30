from datetime import date
from unittest.mock import Mock, call

from errors.models import Notifier, ErrorLogger
from guesty.api import GuestyAPI
from work.api import API
from work.api_examples import CANCEL_JOB
from work.models.repeat_work import (
    RepeatConfig, RepeatWork, RepeatTicket,
    alert_should_have_but_didnt_unblock_background)
from work.models.ticket import NEXT_VACANT_NIGHT, Ticket, REGULAR_MAINTENANCE
from work.tests.test_maintenance import get_test_maintenance
from work.tests.test_rental import get_test_properly_rental
from work.tests.test_ticket import get_test_ticket
from work.tests.test_work import set_work_stuff
from work.tests.test_work_type import get_test_work_type
from work.tests.test_worker import get_test_independent_worker
from rentals.tests import get_test_rental
from reservations.models import Reservation, CANCELED
from reservations.tests import get_test_reservation
from util.signals import post_sync
from util.tests import TestCase
from util.timezone import str_to_tz_dt


checklist_link = (
    'https://app.getproperly.com/#/checklists/DYCB3hlT21/U3ZEGle9vt/')


def get_test_repeat_config(**kwargs):
  properly_rental = kwargs.get('properly_rental', None)
  if not properly_rental:
    properly_rental = get_test_properly_rental(**kwargs)
  work_type = kwargs.get('work_type', None)
  if not work_type:
    work_type = get_test_work_type(**kwargs)

  repeat_config = RepeatConfig(
      title=kwargs.get('title', 'Job title here'),
      properly_rental=properly_rental,
      work_type=work_type,
      checklist_link=kwargs.get(
          'checklist_link',
          'https://app.getproperly.com/#/checklists/DYCB3hlT21/U3ZEGle9vt/'),
      days_between_jobs=kwargs.get('days_between_jobs', 45),
      very_first_job=kwargs.get('very_first_job', date(2018, 10, 15)),
      expected_duration=kwargs.get('expected_duration', 5),
      vacant_night_required=kwargs.get('vacant_night_required', True),
      active=kwargs.get('active', True))
  repeat_config.save()
  return repeat_config


def get_test_repeat_work(**kwargs):
  repeat_config = kwargs.get('repeat_config', None)
  if not repeat_config:
    repeat_config = get_test_repeat_config(**kwargs)

  repeat_work = RepeatWork(
      accepted_by=kwargs.get('accepted_by', None),
      repeat_config=repeat_config,
      job_request_id=kwargs.get('job_request_id', None),
      creation_confirmed=kwargs.get('creation_confirmed', None),
      started_at=kwargs.get('started_at', None),
      completed_at=kwargs.get('completed_at', None),
      offered_start_time=kwargs.get(
          'offered_start_time', str_to_tz_dt('2018-10-15 11:00')))
  return set_work_stuff(repeat_work, **kwargs)


class BlockTests(TestCase):
  def test_alert_should_have_but_didnt_unblock(self):
    guesty_api = Mock(spec=GuestyAPI)
    guesty_api.get_calendar.return_value = [{'status': 'unavailable'}]
    error_logger = Mock(spec=ErrorLogger)
    nnow = str_to_tz_dt('2019-01-15 12:00')

    rental = get_test_rental(
        guesty_id='wewillmakeitwork', nickname='Geniusville')
    work = get_test_repeat_work(
        rental=rental, offered_start_time=str_to_tz_dt('2019-01-16 12:00'),
        canceled_at=str_to_tz_dt('2019-01-10'),
        title='A perfect storm of dysfunction')
    alert_should_have_but_didnt_unblock_background(
        scheduling_api=guesty_api, error_logger=error_logger, nnow=nnow)

    expected_message = (
        '{} A perfect storm of dysfunction at Geniusville on '
        '2019-01-16').format(work.pk)
    expected_call = call(
        'Canceled repeat work didn\'t unblock!', expected_message,
        always_new_error=True)
    self.assertEqual([expected_call], error_logger.log_error.call_args_list)
    self.assertEqual(
        [call('wewillmakeitwork', date(2019, 1, 16), date(2019, 1, 16))],
        guesty_api.get_calendar.call_args_list)

  def test_cancel_unblocks(self):
    worker = get_test_independent_worker()
    # Blocking and unblocking happens in rental.block which references
    # guestyrental.
    repeat_work = get_test_repeat_work(
        job_request_id='asdf', accepted_by=worker,
        vacant_night_required=True, guesty_id='alsnekensl',
        offered_start_time=str_to_tz_dt('2019-01-01 12:00'))

    api = Mock(spec=API)
    api.job_request_cancel.return_value = CANCEL_JOB
    scheduling_api = Mock()

    repeat_work.cancel(
        'Whatever random reason.', api=api, scheduling_api=scheduling_api)
    self.assertEqual(
        [call('alsnekensl', date(2019, 1, 1))],
        scheduling_api.unblock.call_args_list)


class OverlapTests(TestCase):
  def test_get_overlap(self):
    rental = get_test_rental()
    reservation = get_test_reservation(
        rental=rental, check_in=str_to_tz_dt('2018-10-15 16:00'),
        check_out=str_to_tz_dt('2018-10-17 11:00'))
    repeat_config = get_test_repeat_config(rental=rental)
    repeat_work = get_test_repeat_work(
        repeat_config=repeat_config, vacant_night_required=True,
        offered_start_time=str_to_tz_dt('2018-10-15 12:00'),
        expected_duration=1)
    self.assertEqual(
        [repeat_work], list(RepeatWork.objects.get_overlap(reservation)))
    repeat_config.vacant_night_required = False
    repeat_config.save()
    self.assertEqual([], list(RepeatWork.objects.get_overlap(reservation)))
    repeat_work.offered_start_time = str_to_tz_dt('2018-10-16 12:00')
    repeat_work.save()
    self.assertEqual(
        [repeat_work], list(RepeatWork.objects.get_overlap(reservation)))
    repeat_work.offered_start_time = str_to_tz_dt('2018-10-17 11:00')
    repeat_work.save()
    self.assertEqual([], list(RepeatWork.objects.get_overlap(reservation)))

    repeat_work.offered_start_time = str_to_tz_dt('2018-10-16 12:00')
    repeat_work.save()
    self.assertEqual(
        [repeat_work], list(RepeatWork.objects.get_overlap(reservation)))
    reservation.status = CANCELED
    reservation.canceled_at = str_to_tz_dt('2018-10-16 12:00')
    reservation.save()
    self.assertEqual([], list(RepeatWork.objects.get_overlap(reservation)))

  def test_alert_or_cancel_if_overlap(self):
    rental = get_test_rental()
    reservation = get_test_reservation(
        rental=rental, check_in=str_to_tz_dt('2018-10-15 16:00'),
        check_out=str_to_tz_dt('2018-10-17 11:00'), guesty_id='azbyc')
    properly_rental = get_test_properly_rental(rental=rental)
    repeat_config = get_test_repeat_config(
        rental=rental, vacant_night_required=True,
        properly_rental=properly_rental)
    get_test_repeat_work(  # unaccepted
        repeat_config=repeat_config,
        offered_start_time=str_to_tz_dt('2018-10-15 12:00'), accepted_by=None,
        job_request_id='bloopitybonk')
    get_test_repeat_work(
        repeat_config=repeat_config,
        offered_start_time=str_to_tz_dt('2018-10-15 12:00'),
        accepted_by=get_test_independent_worker())

    notifier = Mock(spec=Notifier)
    api = Mock(spec=API)
    post_sync.send(
        sender=Reservation, instance=reservation, notifier=notifier,
        api=api)

    subject = 'Regularly scheduled maintenance overlaps with reservation'
    message = (
        'https://app.guesty.com/reservations/azbyc/guests\nYou can safely '
        'cancel the maintenance in Properly at '
        'https://app.getproperly.com/#/calendar?_k=kitpls')
    expected_msg = call('tasks@stayd.com', subject, message)
    self.assertEqual([expected_msg], notifier.notify.call_args_list)


class CopyToTicketTests(TestCase):
  def setUp(self):
    super().setUp()
    self.properly_rental = get_test_properly_rental(
        properly_property_id='bloop', source_property_id='bloop',
        guesty_id='whatever_goes_blar')
    self.checklist_link = (
        'https://app.getproperly.com/#/checklists/DYCB3hlT21/U3ZEGle9vt/')
    self.work_type = get_test_work_type()
    self.repeat_config = get_test_repeat_config(
        title='Tartle!', work_type=self.work_type,
        very_first_job=date(2018, 12, 1),
        vacant_night_required=True, properly_rental=self.properly_rental,
        days_between_jobs=30, expected_duration=5,
        checklist_link=self.checklist_link)
    self.repeat_work = get_test_repeat_work(
        repeat_config=self.repeat_config,
        offered_start_time=str_to_tz_dt('2018-12-25 11:15'),
        created_at=str_to_tz_dt('2018-12-23 12:00'))

  def test_canceled(self):
    self.repeat_work.canceled_at = str_to_tz_dt('2018-12-25 11:15')
    self.repeat_work.save()
    self.assertTrue(self.repeat_work.copy_to_ticket())
    self.assertFalse(Ticket.objects.exists())

  def test_ongoing(self):
    self.assertFalse(self.repeat_work.copy_to_ticket())
    self.assertFalse(Ticket.objects.exists())

  def test_completed(self):
    self.repeat_work.completed_at = str_to_tz_dt('2018-12-25 14:00')
    self.repeat_work.save()
    for i in range(2):
      self.assertTrue(self.repeat_work.copy_to_ticket())
    self.assertEqual(1, Ticket.objects.count())
    self.assertEqual(1, RepeatTicket.objects.count())
    ticket = Ticket.objects.first()
    self.assertEqual('Tartle!', ticket.title)
    self.assertEqual(self.properly_rental.rental, ticket.rental)
    self.assertEqual(NEXT_VACANT_NIGHT, ticket.sla)
    self.assertEqual(5, ticket.expected_duration)
    self.assertEqual(self.checklist_link, ticket.existing_checklist_url)
    self.assertEqual(str(self.repeat_work.pk), ticket.external_id)
    self.assertEqual(self.work_type, ticket.work_type)
    self.assertEqual(str_to_tz_dt('2018-12-25 14:00'), ticket.completed_at)
    self.assertEqual(str_to_tz_dt('2018-12-23 12:00'), ticket.created_at)
    self.assertEqual(REGULAR_MAINTENANCE, ticket.came_from)

    RepeatTicket.objects.get(ticket=ticket, config=self.repeat_config)


class CreateTicketTests(TestCase):
  def test_explain_why_cant_create_ticket(self):
    config = get_test_repeat_config(
        active=False, very_first_job=date(2018, 12, 24),
        days_between_jobs=10)
    self.assertEqual(
        'This config is inactive',
        config.explain_why_cant_create_ticket())

    config.active = True
    config.checklist_link = 'http://www.google.com/'
    self.assertEqual(
        'The checklist_link is invalid',
        config.explain_why_cant_create_ticket())

    config.checklist_link = checklist_link
    self.assertEqual(
        'The very first ticket shouldnt go out until 2018-12-24',
        config.explain_why_cant_create_ticket(
            nnow=str_to_tz_dt('2018-12-23 23:59')))

    ticket = get_test_ticket(completed_at=str_to_tz_dt('2018-12-25 12:00'))
    RepeatTicket.objects.create(ticket=ticket, config=config)
    last_time = (
        'Given the last time this was done, the earliest the next ticket '
        'can go out is Jan. 04, 2019, noon')
    self.assertEqual(last_time, config.explain_why_cant_create_ticket(
        nnow=str_to_tz_dt('2018-12-28')))

    ticket.completed_at = None
    ticket.save()
    self.assertEqual(
        'There\'s already an upcoming ticket',
        config.explain_why_cant_create_ticket(
            nnow=str_to_tz_dt('2018-12-28')))

  def test_upcoming_ticket_exists(self):
    config = get_test_repeat_config()
    ticket = get_test_ticket()
    RepeatTicket.objects.create(ticket=ticket, config=config)
    self.assertTrue(config.upcoming_ticket_exists())
    maintenance = get_test_maintenance(
        offered_start_time=str_to_tz_dt('2018-12-25 11:15'))
    ticket.maintenance = maintenance
    ticket.save()
    self.assertTrue(config.upcoming_ticket_exists(
        nnow=str_to_tz_dt('2018-12-25 14:00')))
    self.assertFalse(config.upcoming_ticket_exists(
        nnow=str_to_tz_dt('2018-12-25 23:30')))
    maintenance.started_at = str_to_tz_dt('2018-12-25 11:15')
    maintenance.save()
    self.assertTrue(config.upcoming_ticket_exists(
        nnow=str_to_tz_dt('2018-12-25 23:30')))
    maintenance.completed_at = str_to_tz_dt('2018-12-25 20:00')
    maintenance.save()
    self.assertFalse(config.upcoming_ticket_exists(
        nnow=str_to_tz_dt('2018-12-25 23:30')))
    maintenance.canceled_at = maintenance.completed_at
    maintenance.completed_at = None
    maintenance.save()
    self.assertFalse(config.upcoming_ticket_exists(
        nnow=str_to_tz_dt('2018-12-25 23:30')))

  def test_create_ticket(self):
    properly_rental = get_test_properly_rental()
    work_type = get_test_work_type()
    config = get_test_repeat_config(
        title='Look alive Smith!',
        properly_rental=properly_rental,
        work_type=work_type,
        checklist_link=checklist_link,
        expected_duration=7,
        vacant_night_required=True)

    ticket = config.create_ticket()
    self.assertEqual('Look alive Smith!', ticket.title)
    self.assertEqual(properly_rental.rental, ticket.rental)
    self.assertEqual(work_type, ticket.work_type)
    self.assertEqual(checklist_link, ticket.existing_checklist_url)
    self.assertEqual(7, ticket.expected_duration)
    self.assertEqual(NEXT_VACANT_NIGHT, ticket.sla)
    self.assertEqual(REGULAR_MAINTENANCE, ticket.came_from)

    self.assertEqual(1, RepeatTicket.objects.count())
    RepeatTicket.objects.get(ticket=ticket, config=config)
