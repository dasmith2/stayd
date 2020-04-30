from datetime import date, timedelta

from rentals.models import City
from rentals.tests import get_test_rental
from work.models.not_scheduled_reason import not_scheduled_reason_finder
from work.models.sla import NOW, NEXT_CHECKOUT, NEXT_VISIT
from work.models.ticket import DELAYED, COMPLETE
from work.models.ticket import (
    Ticket, TICKETS_PAGE, PROPERLY, REGULAR_MAINTENANCE)
from work.models.ticket_ui import (
    tickets_for_table, tickets_table, edit_ticket_context, REDIRECT_TO_TICKETS,
    TicketFormEverything, TicketFormSLA,
    TicketFormJustNotes, ticket_edit_form, NO_SLA)
from work.tests.test_maintenance import get_test_maintenance
from work.tests.test_ticket import get_test_ticket
from work.tests.test_work_type import get_test_work_type
from util.table import Row, Cell
from util.tests import TestCase
from util.timezone import str_to_tz_dt


class EditTicketTests(TestCase):
  def setUp(self):
    super().setUp()
    self.rental = get_test_rental()

  def test_change_sla_and_notes(self):
    post = {
        'internal_notes': 'How much of this light is advertising?',
        'sla': NEXT_VISIT}
    ticket = get_test_ticket(maintenance=get_test_maintenance(
        offered_start_time=str_to_tz_dt('2018-12-25'),
        started_at=str_to_tz_dt('2018-12-25 00:01')))
    self.assertFalse(ticket.can_edit_everything())
    self.assertEqual(REDIRECT_TO_TICKETS, edit_ticket_context(post, ticket.pk))
    ticket.refresh_from_db()
    self.assertEqual(
        'How much of this light is advertising?', ticket.internal_notes)
    self.assertEqual(NEXT_VISIT, ticket.sla)

  def test_ticket_edit_form(self):
    ticket = get_test_ticket()
    self.assertEqual(TicketFormEverything, ticket_edit_form(pk=None))
    self.assertEqual(TicketFormEverything, ticket_edit_form(pk=ticket.pk))
    ticket.maintenance = get_test_maintenance(
        offered_start_time=str_to_tz_dt('2018-12-25'),
        started_at=str_to_tz_dt('2018-12-25 00:01'))
    ticket.save()
    self.assertEqual(TicketFormSLA, ticket_edit_form(pk=ticket.pk))
    ticket.completed_at = str_to_tz_dt('2018-12-25 02:00')
    ticket.save()
    self.assertEqual(TicketFormJustNotes, ticket_edit_form(pk=ticket.pk))

  def test_new_no_post(self):
    edit_ticket_context(None, None)

  def test_detail(self):
    # New
    post = {
        'title': 'Save the bears',
        'expected_duration': '1',
        'form-0-label': 'By eating them',
        'form-1-label': 'Dont actually eat them',
        'form-INITIAL_FORMS': '0',
        'form-MAX_NUM_FORMS': '1000',
        'form-MIN_NUM_FORMS': '0',
        'form-TOTAL_FORMS': '3',
        'rental': str(self.rental.pk)}
    pk = None
    self.assertEqual(REDIRECT_TO_TICKETS, edit_ticket_context(post, pk))
    ticket = Ticket.objects.first()
    self.assertEqual('Save the bears', ticket.title)
    self.assertEqual(TICKETS_PAGE, ticket.came_from)
    self.assertEqual(2, ticket.checklist.checklistitem_set.count())
    [eat, dont_eat] = ticket.checklist.checklistitem_set.all()
    self.assertEqual('By eating them', eat.label)

    # Change
    post = {
        'title': 'Save the bears!?',
        'expected_duration': '1.00',
        'form-0-id': str(eat.pk),
        'form-0-label': 'By eating them!?',
        'form-1-id': str(dont_eat.pk),
        'form-1-label': 'Dont actually eat them.',
        'form-1-DELETE': 'on',
        'form-2-label': 'Eat this burrito instead',
        'form-INITIAL_FORMS': '2',
        'form-MAX_NUM_FORMS': '1000',
        'form-MIN_NUM_FORMS': '0',
        'form-TOTAL_FORMS': '4',
        'rental': str(self.rental.pk)}
    pk = ticket.pk
    self.assertEqual(REDIRECT_TO_TICKETS, edit_ticket_context(post, pk))

    ticket.refresh_from_db()
    self.assertEqual('Save the bears!?', ticket.title)
    self.assertEqual(2, ticket.checklist.checklistitem_set.count())
    [eat, eat_instead] = ticket.checklist.checklistitem_set.all()
    self.assertEqual('By eating them!?', eat.label)
    self.assertEqual('Eat this burrito instead', eat_instead.label)
    self.assertNotEqual(dont_eat.pk, eat_instead.pk)


class TicketTests(TestCase):
  def setUp(self):
    super().setUp()
    get_test_ticket(created_at=str_to_tz_dt('2018-12-25'))  # Too old
    self.rental = get_test_rental(city='New York', nickname='Daves loft')
    self.work_type = get_test_work_type(name='Planking')
    why_not = not_scheduled_reason_finder.by_name(
        'The blogs arent proofread!1')
    self.new = get_test_ticket(
        title='Emus everywhere',
        rental=self.rental, sla=NOW, work_type=self.work_type,
        created_at=str_to_tz_dt('2019-01-01 12:00'),
        not_scheduled_reason=why_not,
        last_attempt_to_schedule=str_to_tz_dt('2019-01-01 12:05'),
        came_from=TICKETS_PAGE)
    self.assertEqual(
        DELAYED, self.new.status(nnow=str_to_tz_dt('2019-01-02 12:00')))
    self.maintenance = get_test_maintenance(
        job_request_id='asdfasdf',
        offered_start_time=str_to_tz_dt('2019-01-03 12:00'))
    other_rental = get_test_rental(city='L.A.', nickname='Marcs Palace')
    self.offered = get_test_ticket(
        title='Tune the piano',
        rental=other_rental, sla=NEXT_VISIT,
        work_type=get_test_work_type(name='Splunking'),
        created_at=str_to_tz_dt('2019-01-01 12:00'),
        completed_at=str_to_tz_dt('2019-01-01 14:05'),
        completed_by_description='Steve on work.hihoward.com',
        maintenance=self.maintenance,
        last_attempt_to_schedule=str_to_tz_dt('2019-01-01 12:05'),
        came_from=PROPERLY)
    self.assertEqual(COMPLETE, self.offered.status())


class TicketsForTableOrderTests(TestCase):
  def test_order(self):
    completed = get_test_ticket(
        completed_at=str_to_tz_dt('2018-12-25 12:00'),
        created_at=str_to_tz_dt('2018-12-25'))
    scheduled = get_test_ticket(maintenance=get_test_maintenance(
        offered_start_time=str_to_tz_dt('2018-12-28 12:00')),
        created_at=str_to_tz_dt('2018-12-26'))
    created = get_test_ticket(created_at=str_to_tz_dt('2018-12-27'))
    self.assertEqual(
        [scheduled, created, completed],
        tickets_for_table(date(2018, 12, 1), date(2019, 1, 1)))


class TicketsForTableTests(TicketTests):
  def test_filters(self):
    # First, filter by everything to make sure they all let a valid result
    # through
    not_scheduled_reason = not_scheduled_reason_finder.by_name(
        'The blogs arent proofread!1')
    new_york = City.objects.get(name='New York')
    self.assertEqual([self.new], list(tickets_for_table(
        date(2019, 1, 1), date(2019, 2, 1), slas=[NOW], statuses=[DELAYED],
        not_scheduled_reason_ids=[str(not_scheduled_reason.pk)],
        came_from=TICKETS_PAGE,
        cities=[new_york], building_ids=[str(self.rental.building.pk)],
        rental_ids=[str(self.rental.pk)])))

    # Then test each filter one by one to make sure each doesn't let an invalid
    # result through.
    self.assertEqual([], list(tickets_for_table(
        date(2019, 1, 1), date(2019, 2, 1), slas=[NEXT_CHECKOUT])))
    self.assertEqual([], list(tickets_for_table(
        date(2019, 1, 1), date(2019, 2, 1), statuses=['whatever'])))
    self.assertEqual([], list(tickets_for_table(
        date(2019, 1, 1), date(2019, 2, 1),
        not_scheduled_reason_ids=['1000'])))
    self.assertEqual([], list(tickets_for_table(
        date(2019, 1, 1), date(2019, 2, 1), came_from=REGULAR_MAINTENANCE)))
    self.assertEqual([], list(tickets_for_table(
        date(2019, 1, 1), date(2019, 2, 1), cities=['London'])))
    self.assertEqual([], list(tickets_for_table(
        date(2019, 1, 1), date(2019, 2, 1), building_ids=['1000'])))
    self.assertEqual([], list(tickets_for_table(
        date(2019, 1, 1), date(2019, 2, 1), rental_ids=['1000'])))
    self.assertEqual([], list(tickets_for_table(
        date(2019, 2, 1), date(2019, 3, 1))))

    # Test NO SLA
    self.offered.sla = ''
    self.offered.save()
    self.assertEqual([self.offered], list(tickets_for_table(
        date(2019, 1, 1), date(2019, 2, 1), slas=[NO_SLA])))


class TicketTableTests(TicketTests):
  def test_ticket_table(self):
    table = tickets_table(
        [self.new, self.offered], nnow=str_to_tz_dt('2019-01-02 12:00'))
    scheduled_for_header = Cell(
        'Scheduled for', classes=['sorted'], is_header=True)
    expected_headers = [
        'Title', 'City', 'Rental', 'SLA', 'Status', 'Created', 'Completed on',
        'Completed by', 'Time to completion', 'Maintenance job',
        scheduled_for_header, 'Last schedule attempt', 'Why can\'t schedule',
        'Came from']
    self.assertEqual(expected_headers, table.headers)
    self.assertEqual(2, len(table.rows))
    sla_0 = Cell(
        NOW, additional_attrs={'data-can-edit-sla': True}, classes=['sla'])
    table.rows[0].assertEqual(Row(cells=[
        Cell('Emus everywhere', url='/ticket/{}/'.format(self.new.pk)),
        'New York', 'Daves loft', sla_0, DELAYED,
        str_to_tz_dt('2019-01-01 12:00'), None, '', None, Cell(), None,
        str_to_tz_dt('2019-01-01 12:05'), 'The blogs arent proofread!1',
        TICKETS_PAGE], additional_attrs={'data-pk': self.new.pk}))
    url = '/admin/work/maintenance/{}/change/'.format(self.maintenance.pk)
    sla_1 = Cell(
        NEXT_VISIT, additional_attrs={'data-can-edit-sla': True},
        classes=['sla'])
    table.rows[1].assertEqual(Row(cells=[
        Cell('Tune the piano', url='/ticket/{}/'.format(self.offered.pk)),
        'L.A.', 'Marcs Palace', sla_1, COMPLETE,
        str_to_tz_dt('2019-01-01 12:00'), str_to_tz_dt('2019-01-01 14:05'),
        'Steve on work.hihoward.com', timedelta(hours=2, minutes=5),
        Cell('Tune the piano', url=url), str_to_tz_dt('2019-01-03 12:00'),
        str_to_tz_dt('2019-01-01 12:05'),
        None, PROPERLY], additional_attrs={'data-pk': self.offered.pk}))
