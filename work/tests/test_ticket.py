from datetime import timedelta
import json
from unittest.mock import Mock, call

from django.conf import settings
from django.core.exceptions import ValidationError

from photos.s3 import S3
from photos.tests import set_photo_stuff
from rentals.tests import get_test_rental
from work.api_examples import TASK_UPDATED, PROBLEM_REPORTED
from work.models.message import (
    Message, MessageSender, INFORM_OF_TICKET_COUNT_NO_SLA, EMAIL)
from work.models.not_scheduled_reason import not_scheduled_reason_finder
from work.models.raw_event import RawEvent
from work.models.sla import NOW, NEXT_VISIT, DONT_SCHEDULE
from work.models.ticket import (
    email_no_sla_ticket_count, Ticket, TicketPhoto,
    DELAYED, PRIORITIZED, NEW, INCOMPLETE, NOT_OUR_RESPONSIBILITY,
    THIS_TICKET_LACKS_SLA,
    PROPERLY, TICKETS_PAGE)
from work.models.work import ACCEPTED, STARTED, COMPLETE
from work.tests.test_maintenance_checklist import (
    get_test_maintenance_checklist)
from work.tests.test_cleaning import get_test_cleaning
from work.tests.test_maintenance import get_test_maintenance
from work.tests.test_rental import get_test_properly_rental
from work.tests.test_work_co import get_test_work_co
from work.tests.test_work_co_worker import get_test_work_co_worker
from work.tests.test_work_type import get_test_work_type
from work.tests.test_worker import get_test_independent_worker
from util.tests import TestCase
from util.timezone import str_to_tz_dt


EXAMPLE_CHECKLIST_URL = (
    'https://app.getproperly.com/#/checklists/vysjlbB73W/iQb2SQqIJF/')


def get_test_ticket(**kwargs):
  rental = kwargs.get('rental', None)
  if not rental:
    rental = get_test_properly_rental(**kwargs).rental
  title = (
      'Last time I checked we dont have a lot of songs that feature the '
      'cowbell')
  ticket = Ticket.objects.create(
      maintenance=kwargs.get('maintenance', None),
      rental=rental,
      title=kwargs.get('title', title),
      sla=kwargs.get('sla', ''),
      manual_start_time=kwargs.get('manual_start_time', None),
      checklist=kwargs.get('checklist', None),
      came_from=kwargs.get('came_from', TICKETS_PAGE),
      external_id=kwargs.get('external_id', ''),
      image_url=kwargs.get('image_url', ''),
      existing_checklist_url=kwargs.get('existing_checklist_url', ''),
      expected_duration=kwargs.get('expected_duration', 1),
      internal_notes=kwargs.get('internal_notes', ''),
      appendix=kwargs.get('appendix', ''),
      work_type=kwargs.get('work_type', None),
      not_our_responsibility=kwargs.get('not_our_responsibility', ''),
      completed_at=kwargs.get('completed_at', None),
      completed_by_description=kwargs.get('completed_by_description', ''),
      last_attempt_to_schedule=kwargs.get('last_attempt_to_schedule', None),
      not_scheduled_reason=kwargs.get('not_scheduled_reason', None))

  if 'created_at' in kwargs:
    Ticket.objects.filter(pk=ticket.pk).update(created_at=kwargs['created_at'])
    ticket.refresh_from_db()

  if 'offered_to' in kwargs:
    ticket.offered_to.set(kwargs['offered_to'])

  return ticket


def get_test_ticket_photo(**kwargs):
  ticket = kwargs.get('ticket', None)
  if not ticket:
    ticket = get_test_ticket(**kwargs)
  photo = TicketPhoto(ticket=ticket)
  set_photo_stuff(photo, **kwargs)
  return photo


class EmailNoSlaTicketCountTests(TestCase):
  def email_no_sla_ticket_count_test(self):
    get_test_ticket(sla=NOW, created_at=str_to_tz_dt('2019-01-01'))
    get_test_ticket(sla='', created_at=str_to_tz_dt('2019-02-01'))
    get_test_ticket(sla='', created_at=str_to_tz_dt('2019-03-01'))

    message_sender = Mock(spec=MessageSender)
    email_no_sla_ticket_count(message_sender=message_sender)
    message = Message.objects.get(
        to=settings.EMAIL_TWICE_DAILY_SLA_LESS_TICKET_COUNT,
        reason=INFORM_OF_TICKET_COUNT_NO_SLA, kind=EMAIL)
    self.assertEqual([call(message)], message_sender.send.call_args_list)
    not_scheduled_reason = not_scheduled_reason_finder.by_name(
        THIS_TICKET_LACKS_SLA)
    expected_content = (
        'These tickets need an SLA before we can fix them:\n\n'
        'https://keystothekingdom.hihoward.com/tickets/02-01-2019/03-02-2019/'
        '?not_scheduled_reason_id={}').format(not_scheduled_reason.pk)
    self.assertEqual(expected_content, message.content)
    expected_subject = (
        'Please look at these 2 tickets because they lack an SLA')
    self.assertEqual(expected_subject, message.subject)

  def if_none_exist_do_nothing(self):
    message_sender = Mock(spec=MessageSender)
    email_no_sla_ticket_count(message_sender=message_sender)
    self.assertFalse(Message.objects.exists())


class AutoCreateTests(TestCase):
  def test_problem_reported(self):
    work_co = get_test_work_co(name='The Cleveland Cleaners')
    work_co_worker = get_test_work_co_worker(
        work_co=work_co, email='nikolagirl@yahoo.com', name='Angela F')
    rental = get_test_rental()
    get_test_cleaning(
        job_request_id='5cffe19414b48ac5b66f1fce', rental=rental,
        accepted_by=work_co_worker, offered_to=[work_co_worker])

    raw = RawEvent.objects.create(json=json.dumps(PROBLEM_REPORTED))
    for i in range(2):
      raw.handle()

    self.assertEqual(3, Ticket.objects.count())
    image_url = (
        'https://res.cloudinary.com/dnsuxxqz1/image/upload/app/'
        'hBme0JEoESpgaHTcjeD14XyamFQIMhhN.jpg')
    notes = (
        'Reported by Angela F nikolagirl@yahoo.com who works for '
        'The Cleveland Cleaners')
    Ticket.objects.get(
        rental=rental, title="doesn't show channels", internal_notes=notes,
        sla='', external_id='5cfff0dac27abf0b34ca6dce', came_from=PROPERLY,
        image_url=image_url)
    Ticket.objects.get(
        rental=rental, title='the apartment has an awful smell',
        internal_notes=notes, sla='', external_id='5cffff24c27abf56deca75a6',
        came_from=PROPERLY, image_url='')
    Ticket.objects.get(
        rental=rental,
        title="mirror off track,couldn't figure out how to get it on.",
        internal_notes=notes, sla='', external_id='5d00105483dddd2e76e493b6',
        came_from=PROPERLY, image_url='')


class DuplicateTests(TestCase):
  def test_duplicate(self):
    rental = get_test_rental()
    maintenance = get_test_maintenance(
        job_request_id='whatever',
        offered_start_time=str_to_tz_dt('2018-12-25 11:15'))
    checklist = get_test_maintenance_checklist(checklist_id='candy_crusted')
    indep_worker = get_test_independent_worker(buildings=[rental.building])
    not_scheduled_reason = not_scheduled_reason_finder.by_name(
        THIS_TICKET_LACKS_SLA)
    ticket = get_test_ticket(
        maintenance=maintenance,
        title='Cans of worms',
        rental=rental,
        sla=NOW,
        expected_duration=2,
        checklist=checklist,
        offered_to=[indep_worker],
        created_at=str_to_tz_dt('2018-12-25 10:00'),
        completed_at=str_to_tz_dt('2018-12-25 11:30'),
        last_attempt_to_schedule=str_to_tz_dt('2018-12-25 10:30'),
        not_scheduled_reason=not_scheduled_reason)
    dupe = ticket.duplicate()
    self.assertIsNone(dupe.maintenance)
    self.assertEqual('Cans of worms', dupe.title)
    self.assertEqual(rental, dupe.rental)
    self.assertEqual('', dupe.sla)
    self.assertEqual(2, dupe.expected_duration)
    self.assertEqual(checklist, dupe.checklist)
    self.assertEqual(1, dupe.offered_to.count())
    self.assertEqual(
        indep_worker, dupe.offered_to.first().get_child_class_instance())
    self.assertNotEqual(str_to_tz_dt('2018-12-25 10:00'), dupe.created_at)
    self.assertIsNone(dupe.completed_at)
    self.assertIsNone(dupe.last_attempt_to_schedule)
    self.assertEqual(None, dupe.not_scheduled_reason)


class TestAutoMarkComplete(TestCase):
  def setUp(self):
    super().setUp()
    self.maintenance = get_test_maintenance(
        job_request_id='5cdaf5ba898e99009693f898',
        offered_start_time=str_to_tz_dt('2018-12-25 11:15'))
    self.raw_event = RawEvent.objects.create(json=json.dumps(TASK_UPDATED))

  def test_auto_mark_complete_checklist(self):
    checklist = get_test_maintenance_checklist(
        checklist_id='5cdaf5b6898e99ca0693f892')
    ticket = get_test_ticket(maintenance=self.maintenance, checklist=checklist)

    self.raw_event.handle()

    ticket.refresh_from_db()
    self.assertTrue(ticket.completed_at)

  def test_auto_mark_complete_existing_checklist_url(self):
    existing_checklist_url = (
        'https://app.getproperly.com/#/checklists/5cdaf5b6898e99ca0693f892/'
        '5cdaf5b7f777f6d7a82dbecb/')
    ticket = get_test_ticket(
        maintenance=self.maintenance,
        existing_checklist_url=existing_checklist_url)

    self.raw_event.handle()

    ticket.refresh_from_db()
    self.assertTrue(ticket.completed_at)


class TicketTests(TestCase):
  def test_cant_save_sla_and_manual_start_time(self):
    rental = get_test_rental()
    try:
      Ticket(
          sla=NOW, manual_start_time=str_to_tz_dt('2018-12-25 12:00'),
          rental=rental).clean()
      self.fail()
    except ValidationError:
      pass
    Ticket(
        manual_start_time=str_to_tz_dt('2018-12-25 12:00'),
        rental=rental).clean()

  def test_status(self):
    work_type = get_test_work_type()
    checklist = get_test_maintenance_checklist()
    worker = get_test_independent_worker()
    self.assertEqual(NEW, get_test_ticket().status())
    self.assertEqual(PRIORITIZED, get_test_ticket(
        sla=NOW, checklist=checklist, work_type=work_type).status())
    delayed = get_test_ticket(
        sla=NOW, checklist=checklist, work_type=work_type,
        created_at=str_to_tz_dt('2018-12-01 12:00'))
    self.assertEqual(
        DELAYED, delayed.status(nnow=str_to_tz_dt('2018-12-01 16:01')))

    not_ours = get_test_ticket(
        not_our_responsibility='This is clearly Bob\'s responsibility.',
        sla=DONT_SCHEDULE)
    # Regardless of SLA
    self.assertEqual(NOT_OUR_RESPONSIBILITY, not_ours.status())
    not_ours.completed_at = str_to_tz_dt('2018-12-25 12:00')
    not_ours.save()
    self.assertEqual(COMPLETE, not_ours.status())

    done_maintenance = get_test_maintenance(
        completed_at=str_to_tz_dt('2018-12-25 12:00'),
        job_request_id='sldiadensdl',
        offered_start_time=str_to_tz_dt('2018-12-25 10:00'))
    incomplete = get_test_ticket(
        sla=NEXT_VISIT, checklist=checklist, work_type=work_type,
        maintenance=done_maintenance)
    self.assertEqual(INCOMPLETE, incomplete.status())
    offered_maintenance = get_test_maintenance(
        offered_to=[worker], job_request_id='fnfnfnfnfn',
        offered_start_time=str_to_tz_dt('2018-12-25 11:15'))
    offered = get_test_ticket(
        sla=NEXT_VISIT, checklist=checklist, work_type=work_type,
        maintenance=offered_maintenance)
    self.assertEqual(
        PRIORITIZED, offered.status(nnow=str_to_tz_dt('2018-12-25 11:15')))
    accepted_maintenance = get_test_maintenance(
        accepted_at=str_to_tz_dt('2018-12-25'), job_request_id='wkekekeke',
        accepted_by=worker,
        offered_start_time=str_to_tz_dt('2018-12-25 11:15'))
    accepted = get_test_ticket(
        sla=NEXT_VISIT, checklist=checklist, work_type=work_type,
        maintenance=accepted_maintenance)
    self.assertEqual(
        ACCEPTED, accepted.status(nnow=str_to_tz_dt('2018-12-25 11:15')))
    started_maintenance = get_test_maintenance(
        accepted_at=str_to_tz_dt('2018-12-25'), job_request_id='wkekekeke',
        accepted_by=worker, started_at=str_to_tz_dt('2018-12-25 12:00'),
        offered_start_time=str_to_tz_dt('2018-12-25 11:15'))
    started = get_test_ticket(
        sla=NEXT_VISIT, checklist=checklist, work_type=work_type,
        maintenance=started_maintenance,
        created_at=str_to_tz_dt('2018-12-24'))
    self.assertEqual(
        STARTED, started.status(nnow=str_to_tz_dt('2018-12-25 11:15')))
    started.completed_at = str_to_tz_dt('2018-12-25 15:15')
    started.save()
    self.assertEqual(
        COMPLETE,
        started.status(nnow=str_to_tz_dt('2018-12-25 16:15')))


class TicketPhotoTests(TestCase):
  def test_stuff(self):
    ticket = get_test_ticket()
    photo = get_test_ticket_photo(
        ticket=ticket, file_name='whos_not_vegan.png')
    ticket.refresh_from_db()
    self.assertEqual(
        'https://dev-hihoward-public.s3.amazonaws.com/whos_not_vegan.png',
        ticket.image_url)
    photo.calc_and_set_keep(nnow=str_to_tz_dt('2019-01-01'))
    self.assertFalse(photo.keep_forever)
    self.assertFalse(photo.sensitive())
    self.assertEqual(
        str_to_tz_dt('2019-01-01') + timedelta(days=30), photo.keep_until)
    self.assertEqual('', photo.explain_why_no_need_for_photo())

    ticket.completed_at = str_to_tz_dt('2019-01-01')
    photo.calc_and_set_keep(nnow=str_to_tz_dt('2019-01-01'))
    self.assertEqual(str_to_tz_dt('2019-01-01'), photo.keep_until)
    self.assertEqual(
        'The ticket has status COMPLETE',
        photo.explain_why_no_need_for_photo())

    photo.delete(s3=Mock(spec=S3))
    ticket.refresh_from_db()
    self.assertEqual('', ticket.image_url)
