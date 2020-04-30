import copy
from decimal import Decimal
import json
from unittest.mock import Mock, call

from django.db.models import Q
from djmoney.money import Money

from rentals.tests import get_test_building, get_test_rental
from util.tests import TestCase
from util.timezone import str_to_tz_dt
from work.api import API
from work.api_examples import CANCELED
from work.models.maintenance_ui import (
    handle_maintenance_post_or_error, maintenance_jobs, maintenance_to_data,
    NewTicketForm, rental_choices, save_new_ticket_form,
    start_new_ticket_form, MORE, LESS, IGotPaidWrongForm,
    submit_i_got_paid_wrong_form)
from work.models.payment import ManualPayment
from work.models.raw_event import RawEvent
from work.models.sla import NEXT_CHECKOUT
from work.models.ticket import Ticket, WORK_NEW_TICKET, WORK_START_TICKET
from work.tests.test_maintenance_checklist import (
    get_test_maintenance_checklist)
from work.tests.test_maintenance import get_test_maintenance
from work.tests.test_rental import get_test_properly_rental
from work.tests.test_ticket import get_test_ticket
from work.tests.test_work_type import get_test_work_type
from work.tests.test_worker import get_test_independent_worker


class IGotPaidWrongTests(TestCase):
  def setUp(self):
    super().setUp()
    self.building = get_test_building(city='Dullsville')
    self.worker = get_test_independent_worker(buildings=[self.building])
    self.post = {
        'building': self.building.pk,
        'amount': Decimal('10'),
        'description': 'Well you see what happened was...'}

  def test_should_get_paid_more(self):
    self.post['more_or_less'] = MORE
    form = IGotPaidWrongForm(self.worker, self.post)
    self.assertTrue(form.is_valid())
    submit_i_got_paid_wrong_form(form, self.worker)
    ManualPayment.objects.get(
        ~Q(on_hold_reason=''), subject='Payment correction',
        message='Well you see what happened was...',
        worker=self.worker, building=self.building,
        amount=Money('10', 'USD'))

  def test_should_get_paid_less(self):
    self.post['more_or_less'] = LESS
    form = IGotPaidWrongForm(self.worker, self.post)
    self.assertTrue(form.is_valid())
    submit_i_got_paid_wrong_form(form, self.worker)
    ManualPayment.objects.get(
        ~Q(on_hold_reason=''), subject='Payment correction',
        message='Well you see what happened was...',
        worker=self.worker, building=self.building,
        amount=Money('-10', 'USD'))


class StartAndSaveNewTicketTests(TestCase):
  def setUp(self):
    super().setUp()
    get_test_rental(building=get_test_building())
    building = get_test_building(city='Dullsville')
    self.rental = get_test_rental(
        building=building, street='123 4th St.', apartment='#5')
    self.worker = get_test_independent_worker(buildings=[building])

  def test_start_new_ticket_form(self):
    form = NewTicketForm(self.worker, {
        'rental': str(self.rental.pk),
        'description': 'Interrupt and argue'})
    self.assertTrue(form.is_valid())
    # Start a new ticket
    start_new_ticket_form(
        form, self.worker, nnow=str_to_tz_dt('2018-12-25 12:00'))
    ticket = Ticket.objects.get(
        rental=self.rental, title='Interrupt and argue',
        came_from=WORK_START_TICKET,
        manual_start_time=str_to_tz_dt('2018-12-25 12:00'),
        offered_to=self.worker)
    self.assertEqual(
        str_to_tz_dt('2018-12-25 12:00'), ticket.maintenance.started_at)
    self.assertIsNone(ticket.maintenance.completed_at)
    self.assertEqual(self.rental, ticket.maintenance.rental)
    self.assertEqual(
        self.worker, ticket.maintenance.accepted_by.get_child_class_instance())
    self.assertEqual(1, len(ticket.maintenance.offered_to.all()))
    self.assertEqual(
        self.worker,
        ticket.maintenance.offered_to.first().get_child_class_instance())

    # Wait, I'm at the same property and notice a second thing wrong. Start
    # that one too.
    form = NewTicketForm(self.worker, {
        'rental': str(self.rental.pk),
        'description': 'Prove stuff with arguments'})
    self.assertTrue(form.is_valid())
    ticket2 = start_new_ticket_form(
        form, self.worker, nnow=str_to_tz_dt('2018-12-25 12:30'))
    self.assertEqual(ticket.maintenance, ticket2.maintenance)

    # Start something at a different property!
    form = NewTicketForm(self.worker, {
        'rental': str(get_test_rental().pk),
        'description': 'Have an interesting life experience'})
    try:
      start_new_ticket_form(
          form, self.worker, nnow=str_to_tz_dt('2018-12-25 12:45'))
      self.fail('That should have caused an exception.')
    except Exception:
      pass

  def test_rental_choices(self):
    choices = rental_choices(self.worker)
    expected = [(self.rental.pk, '123 4th St. #5, Dullsville, ND')]
    self.assertEqual(expected, choices)

  def test_save_new_ticket_form(self):
    form = NewTicketForm(self.worker, {
        'rental': str(self.rental.pk),
        'description': 'Shoot from behind the backboard'})
    self.assertTrue(form.is_valid())
    save_new_ticket_form(form)
    Ticket.objects.get(
        rental=self.rental, title='Shoot from behind the backboard',
        came_from=WORK_NEW_TICKET)


class MaintenanceTestBase(TestCase):
  def setUp(self):
    super().setUp()
    self.building = get_test_building(city='Nowhere')
    self.rental = get_test_rental(
        building=self.building, street='Circling the drain', apartment='#2')
    self.properly_rental = get_test_properly_rental(rental=self.rental)
    self.work_type = get_test_work_type()
    self.worker = get_test_independent_worker(
        buildings=[self.building], work_types=[self.work_type])
    self.work = get_test_maintenance(
        offered_to=[self.worker],
        offered_start_time=str_to_tz_dt('2018-12-25 12:00'),
        job_request_id='jarb')
    checklist = get_test_maintenance_checklist(
        items=['Poke the real live bear with a stick'])
    self.ticket = get_test_ticket(
        maintenance=self.work, sla=NEXT_CHECKOUT, rental=self.rental,
        title='Cans of worms', checklist=checklist,
        appendix='See the internet for details')


class NothingTests(TestCase):
  def test_maintenance_jobs(self):
    maintenance_jobs(get_test_independent_worker())


class DataTests(MaintenanceTestBase):
  def test_my_tickets_data(self):
    got_data = maintenance_to_data(self.work)
    expected_data = {
        'id': self.work.pk,
        'when': 'Tue Dec 25 noon',
        'where': 'Circling the drain #2, Nowhere, ND',
        'started': False,
        'completed': False,
        'high_priority': False,
        'tickets': [{
            'id': self.ticket.pk,
            'image_url': '',
            'title': 'Cans of worms',
            'appendix': 'See the internet for details',
            'complete': None,
            'checklist': ['Poke the real live bear with a stick']}]}
    self.assertEqual(expected_data, got_data)


class PostTests(MaintenanceTestBase):
  def test_start_but_somebody_else_started(self):
    stan = get_test_independent_worker(name='Stan')
    self.work.accepted_by = stan
    self.work.save()
    post = {'start': self.work.pk}
    self.assertEqual(
        'Stan already started this job',
        handle_maintenance_post_or_error(
            post, self.worker,
            nnow=str_to_tz_dt('2018-12-25 12:15')))
    self.work.refresh_from_db()
    self.assertEqual(stan, self.work.accepted_by.get_child_class_instance())

  def test_start_stop(self):
    api = Mock(spec=API)
    # Hey somebody started a job on the new keys maintenance page! Nice.
    post = {'start': self.work.pk}
    self.assertIsNone(handle_maintenance_post_or_error(
        post, self.worker,
        nnow=str_to_tz_dt('2018-12-25 12:15'), api=api))
    self.assertEqual([call('jarb')], api.job_request_cancel.call_args_list)
    self.work.refresh_from_db()
    self.assertTrue(self.work.action_on_keys)
    self.assertFalse(self.work.action_on_properly)
    self.assertEqual(
        self.worker, self.work.accepted_by.get_child_class_instance())
    self.assertEqual(str_to_tz_dt('2018-12-25 12:15'), self.work.started_at)
    self.assertEqual(
        str_to_tz_dt('2018-12-25 12:15'),
        self.work.action_on_keys_canceled_on_properly_at)

    # Since it was canceled on properly, I would expect a canceled webhook back
    # from properly at some point.
    canceled_data = copy.deepcopy(CANCELED)
    canceled_data['results'][0]['jobRequestId'] = 'jarb'
    RawEvent.objects.create(json=json.dumps(canceled_data)).handle()
    self.work.refresh_from_db()
    self.assertIsNone(self.work.canceled_at)

    # They check off a ticket as being done!
    post = {'done': self.ticket.pk}
    self.assertIsNone(handle_maintenance_post_or_error(
        post, self.worker, nnow=str_to_tz_dt('2018-12-25 13:15')))
    self.ticket.refresh_from_db()
    self.assertEqual(
        str_to_tz_dt('2018-12-25 13:15'), self.ticket.completed_at)

    # Oh wait, now they un-check it.
    post = {'not_done': self.ticket.pk}
    self.assertIsNone(handle_maintenance_post_or_error(
        post, self.worker, nnow=str_to_tz_dt('2018-12-25 13:20')))
    self.ticket.refresh_from_db()
    self.assertIsNone(self.ticket.completed_at)

    # Anyway now they're done.
    post = {'stop': self.work.pk}
    self.assertIsNone(handle_maintenance_post_or_error(
        post, self.worker, nnow=str_to_tz_dt('2018-12-25 14:15')))
    self.work.refresh_from_db()
    self.assertEqual(str_to_tz_dt('2018-12-25 14:15'), self.work.completed_at)
    self.assertIsNotNone(self.work.workpayment)

    # They double clicked done. NBD.
    post = {'stop': self.work.pk}
    self.assertIsNone(handle_maintenance_post_or_error(
        post, self.worker, nnow=str_to_tz_dt('2018-12-25 14:15:30')))
    self.work.refresh_from_db()
    self.assertEqual(
        str_to_tz_dt('2018-12-25 14:15:30'), self.work.completed_at)
    self.assertIsNotNone(self.work.workpayment)

    # Wait they aren't done after all!
    post = {'reopen': self.work.pk}
    self.assertIsNone(handle_maintenance_post_or_error(
        post, self.worker, nnow=str_to_tz_dt('2018-12-25 14:16:00')))
    self.work.refresh_from_db()
    self.assertIsNone(self.work.completed_at)
    self.assertIsNone(self.work.workpayment_or_none)


class JobsTests(TestCase):
  def test_jobs(self):
    rental = get_test_rental()
    no_maam = get_test_independent_worker(name='no_maam')
    yes_maam = get_test_independent_worker(name='yes_maam')
    yes_1 = get_test_maintenance(
        offered_to=[yes_maam],
        offered_start_time=str_to_tz_dt('2018-12-25 12:00'),
        accepted_by=yes_maam, rental=rental)
    get_test_ticket(
        maintenance=yes_1, checklist=get_test_maintenance_checklist(),
        rental=rental)
    get_test_ticket(
        maintenance=yes_1, checklist=get_test_maintenance_checklist(),
        rental=rental)
    yes_2 = get_test_maintenance(
        offered_to=[yes_maam, no_maam],
        offered_start_time=str_to_tz_dt('2018-12-29 12:00'), rental=rental)
    get_test_ticket(
        maintenance=yes_2, checklist=get_test_maintenance_checklist(),
        rental=rental)
    get_test_maintenance(  # No tickets.
        offered_to=[yes_maam, no_maam],
        offered_start_time=str_to_tz_dt('2018-12-29 12:00'), rental=rental)
    too_old = get_test_maintenance(
        offered_to=[yes_maam], offered_start_time=str_to_tz_dt('2018-12-01'),
        rental=rental)
    get_test_ticket(
        maintenance=too_old, checklist=get_test_maintenance_checklist(),
        rental=rental)
    completed_already = get_test_maintenance(
        offered_to=[yes_maam, no_maam],
        offered_start_time=str_to_tz_dt('2018-12-25 12:00'),
        completed_at=str_to_tz_dt('2018-12-25 14:00'), rental=rental)
    get_test_ticket(
        maintenance=completed_already,
        checklist=get_test_maintenance_checklist(), rental=rental)
    canceled = get_test_maintenance(
        offered_to=[yes_maam, no_maam],
        offered_start_time=str_to_tz_dt('2018-12-25 12:00'),
        canceled_at=str_to_tz_dt('2018-12-25 14:00'), rental=rental)
    get_test_ticket(
        maintenance=canceled, checklist=get_test_maintenance_checklist(),
        rental=rental)
    somebody_else = get_test_maintenance(
        offered_to=[yes_maam, no_maam],
        offered_start_time=str_to_tz_dt('2018-12-25 12:00'),
        accepted_by=no_maam, rental=rental)
    get_test_ticket(
        maintenance=somebody_else, checklist=get_test_maintenance_checklist(),
        rental=rental)
    offered_others = get_test_maintenance(
        offered_to=[no_maam],
        offered_start_time=str_to_tz_dt('2018-12-25 14:00'), rental=rental)
    get_test_ticket(
        maintenance=offered_others, checklist=get_test_maintenance_checklist(),
        rental=rental)

    self.assertEqual(
        set([yes_1, yes_2]),
        set(maintenance_jobs(yes_maam, nnow=str_to_tz_dt('2018-12-25 16:00'))))
