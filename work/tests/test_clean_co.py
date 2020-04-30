import copy
from datetime import date
import json
from unittest.mock import Mock, call

from django.conf import settings
from django.shortcuts import reverse
from djmoney.money import Money

from paypal.tests import get_successful_payout
from rentals.tests import get_test_rental, get_test_building
from reservations.models import Reservation
from reservations.tests import get_test_reservation
from work.api import API
from work.api_examples import (
    CREATE_JOB, CANCELED_BY_CLEANER, DECLINED_BY_WORKER, BOOKING_CREATE)
from work.models.cleaning import Cleaning
from work.models.clean_co import (
    explain_why_cant_assign_cleaning_to, assign_cleaning_to,
    handle_cleaner_save, assign_cleanings_table, my_cleanings_table,
    all_rentals_table, handle_edit_cleaning_post, clean_co_can_edit_cleaning,
    CleaningForm, current_res_lookup, next_res_w_cleaning_lookup)
from work.models.message import (
    Message, MessageSender, CLEAN_CO_CLEANING_NEEDS_CLEANER_ASAP,
    NEW_CLEAN_CO_WORKER, CHECKOUT_TIME_CHANGED_SO_REASSIGN)
from work.models.raw_event import RawEvent
from work.models.work import CREATED
from work.models.work_co_worker import WorkCoWorker
from work.models.work_line_item import get_work_line_item_formset_data
from work.models.work_type import WorkType
from work.tests.test_clean import get_test_did_slide
from work.tests.test_cleaning import (
    get_test_cleaning, get_test_cleaning_config)
from work.tests.test_cleaning_checklist import get_test_cleaning_checklist
from work.tests.test_rental import get_test_properly_rental
from work.tests.test_work_co import get_test_work_co
from work.tests.test_work_co_worker import get_test_work_co_worker
from work.tests.test_worker import get_test_independent_worker
from util.email import EmailSender
from util.signals import post_sync
from util.table import Row, Cell
from util.tests import TestCase, get_test_user
from util.timezone import str_to_tz_dt


class SaveCleaningTests(TestCase):
  def setUp(self):
    super().setUp()
    building = get_test_building(nickname='The Hive')
    self.rental = get_test_rental(
        nickname='The Hive #456', apartment='#456', building=building)
    self.clean_co = get_test_work_co(name='Susans Scrubbers')
    self.worker = get_test_work_co_worker(
        work_co=self.clean_co, name='The Cleaninator')
    self.properly_rental = get_test_properly_rental(
        clean_co=self.clean_co, rental=self.rental)
    get_test_cleaning_config(properly_rental=self.properly_rental)
    self.api = Mock(spec=API)

  def test_clean_co_can_edit_cleaning(self):
    wrong_rental = get_test_cleaning(
        offered_start_time=str_to_tz_dt('2018-12-20'))
    self.assertFalse(clean_co_can_edit_cleaning(
        self.clean_co, wrong_rental, nnow=str_to_tz_dt('2018-12-25')))

    past_not_paid_out_yet = get_test_cleaning(
        offered_start_time=str_to_tz_dt('2018-12-20'),
        accepted_by=self.worker, started_at=str_to_tz_dt('2018-12-20 11:15'),
        completed_at=str_to_tz_dt('2018-12-20 14:05'),
        rental=self.rental)
    self.assertTrue(clean_co_can_edit_cleaning(
        self.clean_co, past_not_paid_out_yet, nnow=str_to_tz_dt('2018-12-25')))

    past_paid_out = get_test_cleaning(
        offered_start_time=str_to_tz_dt('2018-12-20'),
        accepted_by=self.worker, started_at=str_to_tz_dt('2018-12-20 11:15'),
        completed_at=str_to_tz_dt('2018-12-20 14:05'),
        rental=self.rental)
    past_paid_out.workpayment.paypal_payout = get_successful_payout()
    past_paid_out.workpayment.save()
    self.assertFalse(clean_co_can_edit_cleaning(
        self.clean_co, past_paid_out, nnow=str_to_tz_dt('2018-12-25')))

    future_properly_canceled = get_test_cleaning(
        job_request_id='whatever_3',
        offered_start_time=str_to_tz_dt('2019-01-01'),
        canceled_at=str_to_tz_dt('2018-12-24'),
        permanently_canceled_reason='wah!', rental=self.rental)
    self.assertTrue(clean_co_can_edit_cleaning(
        self.clean_co, future_properly_canceled,
        nnow=str_to_tz_dt('2018-12-25')))

    future_not_properly = get_test_cleaning(
        offered_start_time=str_to_tz_dt('2019-01-01'), rental=self.rental)
    self.assertTrue(clean_co_can_edit_cleaning(
        self.clean_co, future_not_properly, nnow=str_to_tz_dt('2018-12-25')))

    # New cleaning
    self.assertTrue(clean_co_can_edit_cleaning(
        clean_co=self.clean_co, cleaning=None))

  def test_edit_reservationless_cleaning(self):
    cleaning = get_test_cleaning(
        offered_start_time=str_to_tz_dt('2018-12-25 12:00'),
        rental=self.rental,
        reservation=None)
    data = get_work_line_item_formset_data(cleaning)
    data.update({
        'assigned_to': str(self.worker.pk),
        'day': '2018-12-20',
        'started_at': '11:45',
        'completed_at': '14:05',
        'save': 'Save',
        'where': str(self.rental.pk)})
    handle_edit_cleaning_post(
        data, clean_co=self.clean_co, cleaning=cleaning,
        nnow=str_to_tz_dt('2019-01-01 11:15'))

    # This just helps point out why it might not have saved.
    CleaningForm(self.clean_co, cleaning, data).my_clean()
    cleaning.refresh_from_db()
    self.assertEqual(str_to_tz_dt('2018-12-20 11:45'), cleaning.started_at)

  def test_save_new_past_cleaning(self):
    data = {
        'assigned_to': str(self.worker.pk),
        'started_at': '11:45',
        'completed_at': '14:05',
        'day': '2018-12-20',
        'save': 'Save',
        'where': str(self.rental.pk),
        'li-MAX_NUM_FORMS': '',
        'li-INITIAL_FORMS': '0',
        'li-TOTAL_FORMS': 1,
        'li-0-pk': '',
        'li-0-amount': '10',
        'li-0-description': 'New sponge!'}
    result = handle_edit_cleaning_post(
        data, clean_co=self.clean_co, cleaning=None,
        nnow=str_to_tz_dt('2018-12-25 12:00'))
    self.assertTrue(result.saved)
    self.assertFalse(result.canceled)
    self.assertFalse(result.reopened)
    cleaning = result.cleaning
    self.assertEqual('', cleaning.job_request_id)
    self.assertEqual(self.rental, cleaning.rental)
    self.assertEqual(self.worker, cleaning.accepted_by)
    self.assertEqual(str_to_tz_dt('2018-12-20 11:45'), cleaning.started_at)
    self.assertEqual(str_to_tz_dt('2018-12-20 14:05'), cleaning.completed_at)
    self.assertEqual(1, cleaning.worklineitem_set.count())
    wli = cleaning.worklineitem_set.first()
    self.assertEqual(Money('10', 'USD'), wli.amount)
    self.assertEqual('New sponge!', wli.description)

  def test_future_canceled_cleaning_reopen(self):
    cleaning = get_test_cleaning(
        offered_start_time=str_to_tz_dt('2019-01-01 11:15'),
        canceled_at=str_to_tz_dt('2018-12-21 12:00'),
        offered_to=[self.worker], rental=self.rental,
        job_request_id='harkenabonkina',
        permanently_canceled_reason='Whatever')
    data = {'uncancel': 'This cleaning will actually happen'}
    result = handle_edit_cleaning_post(
        data, self.clean_co, cleaning, nnow=str_to_tz_dt('2018-12-25'))
    self.assertEqual('', result.cleaning.permanently_canceled_reason)
    self.assertIsNone(result.cleaning.canceled_at)
    self.assertEqual('', result.cleaning.job_request_id)

  def test_past_canceled_cleaning_actually_happened_and_save_cleaning(self):
    cleaning = get_test_cleaning(
        offered_start_time=str_to_tz_dt('2018-12-20 11:15'),
        canceled_at=str_to_tz_dt('2018-12-21 12:00'),
        offered_to=[self.worker], rental=self.rental)
    data = {'uncancel': 'This cleaning actually happened'}
    result = handle_edit_cleaning_post(
        data, self.clean_co, cleaning, nnow=str_to_tz_dt('2018-12-25'))
    self.assertFalse(result.saved)
    self.assertFalse(result.canceled)
    self.assertTrue(result.reopened)
    cleaning = result.cleaning
    self.assertIsNone(cleaning.canceled_at)

    data = {
        'assigned_to': str(self.worker.pk),
        'started_at': '11:45',
        'completed_at': '14:05',
        'day': '2018-12-20',
        'save': 'Save',
        'where': str(self.rental.pk),
        'li-MAX_NUM_FORMS': '',
        'li-INITIAL_FORMS': '0',
        'li-TOTAL_FORMS': 1,
        'li-0-pk': '',
        'li-0-amount': '',
        'li-0-description': ''}
    result = handle_edit_cleaning_post(
        data, self.clean_co, cleaning, nnow=str_to_tz_dt('2018-12-25'))
    cleaning = result.cleaning
    self.assertEqual(str_to_tz_dt('2018-12-20 11:45'), cleaning.started_at)
    self.assertEqual(str_to_tz_dt('2018-12-20 14:05'), cleaning.completed_at)

  def test_save_new_future_cleaning(self):
    data = {
        'assigned_to': str(self.worker.pk),
        'day': '2019-01-01',
        'save': 'Save',
        'where': str(self.rental.pk),
        'li-MAX_NUM_FORMS': '',
        'li-INITIAL_FORMS': '0',
        'li-TOTAL_FORMS': 1,
        'li-0-pk': '',
        'li-0-amount': '10',
        'li-0-description': 'New sponge!'}
    result = handle_edit_cleaning_post(
        data, clean_co=self.clean_co, cleaning=None,
        nnow=str_to_tz_dt('2018-12-25 12:00'))
    self.assertTrue(result.saved)
    cleaning = result.cleaning
    self.assertEqual('', cleaning.job_request_id)
    self.assertEqual(1, cleaning.offered_to.count())
    self.assertEqual(
        self.worker, cleaning.offered_to.first().get_child_class_instance())
    self.assertEqual(None, cleaning.accepted_by)
    self.assertEqual(None, cleaning.started_at)
    self.assertEqual(None, cleaning.completed_at)
    self.assertEqual(1, cleaning.worklineitem_set.count())

  def test_save_future_cleaning_not_in_properly(self):
    cleaning = get_test_cleaning(
        offered_start_time=str_to_tz_dt('2019-01-01 11:15'),
        offered_to=[self.worker], rental=self.rental, job_request_id='')
    new_worker = get_test_work_co_worker(
        work_co=self.clean_co, name='The Scrubist')
    data = {
        'assigned_to': str(new_worker.pk),
        'day': '2019-01-01',
        'save': 'Save',
        'where': str(self.rental.pk),
        'li-MAX_NUM_FORMS': '',
        'li-INITIAL_FORMS': '0',
        'li-TOTAL_FORMS': 1,
        'li-0-pk': '',
        'li-0-amount': '',
        'li-0-description': ''}
    result = handle_edit_cleaning_post(
        data, self.clean_co, cleaning,
        nnow=str_to_tz_dt('2018-12-25'))
    self.assertEqual(1, result.cleaning.offered_to.count())
    self.assertEqual(
        new_worker,
        result.cleaning.offered_to.first().get_child_class_instance())
    self.assertEqual(0, result.cleaning.worklineitem_set.count())

  def test_save_future_cleaning_in_properly(self):
    cleaning = get_test_cleaning(
        offered_start_time=str_to_tz_dt('2019-01-01 11:15'),
        offered_to=[self.worker], rental=self.rental,
        job_request_id='abfaBAbaba')
    data = {
        'assigned_to': str(self.worker.pk),
        'day': '2019-01-01',
        'save': 'Save',
        'where': str(self.rental.pk)}
    try:
      handle_edit_cleaning_post(
          data, self.clean_co, cleaning,
          nnow=str_to_tz_dt('2018-12-25'))
      self.fail('You arent supposed to be able to save properly cleanings')
    except Exception:
      pass

  def test_cancel_cleaning(self):
    cleaning = get_test_cleaning(
        offered_start_time=str_to_tz_dt('2019-01-01 11:15'),
        offered_to=[self.worker], rental=self.rental,
        job_request_id='abfaBAbaba')
    data = {'cancel': 'Cancel this cleaning'}
    result = handle_edit_cleaning_post(
        data, self.clean_co, cleaning,
        nnow=str_to_tz_dt('2018-12-25'), api=self.api)
    self.assertFalse(result.saved)
    self.assertTrue(result.canceled)
    self.assertFalse(result.reopened)
    self.assertIsNotNone(result.cleaning.canceled_at)
    self.assertTrue(bool(result.cleaning.permanently_canceled_reason))


class AllUnitsTests(TestCase):
  def setUp(self):
    super().setUp()
    building = get_test_building(nickname='The Hive')
    self.clean_co = get_test_work_co(name='Susans Scrubbers')
    properly_rental_1 = get_test_properly_rental(
        nickname='The Hive #456', apartment='#456', clean_co=self.clean_co,
        bathrooms=2, bedrooms=3, building=building)
    get_test_properly_rental(
        nickname='The Hive #789', apartment='#789', clean_co=self.clean_co,
        bathrooms=1, bedrooms=1, building=building)
    get_test_properly_rental(nickname='Unrelated', apartment='-1')
    # I assume a guest is in the room for current confirmed reservations.
    get_test_reservation(
        rental=properly_rental_1.rental,
        check_in=str_to_tz_dt('2018-12-25 16:00'),
        check_out=str_to_tz_dt('2018-12-27 11:00'))
    # Don't show an upcoming reservation until it has a cleaning because
    # otherwise cleaning companies will get confused because this tab says
    # there's a reservation but the Cleanings tab doesn't show a cleaning.
    get_test_cleaning(reservation=get_test_reservation(
        rental=properly_rental_1.rental,
        check_in=str_to_tz_dt('2018-12-28 16:00'),
        check_out=str_to_tz_dt('2018-12-29 11:00')))

  def test_all_rentals_table(self):
    table = all_rentals_table(
        self.clean_co, nnow=str_to_tz_dt('2018-12-26 12:00'))
    self.assertEqual([
        'Building', 'Rental', 'Bedrooms', 'Bathrooms', 'Vacant',
        'Current check out', 'Total nights', 'Next check in',
        'Total nights'], table.headers)
    self.assertEqual(2, len(table.rows))
    expected_rows_0 = [
        'The Hive', '#456', 3, 2, False, str_to_tz_dt('2018-12-27 11:00'), 2,
        str_to_tz_dt('2018-12-28 16:00'), 1]
    self.assertEqual(expected_rows_0, table.rows[0].cells)
    expected_rows_1 = ['The Hive', '#789', 1, 1, True, None, None, None, None]
    self.assertEqual(expected_rows_1, table.rows[1].cells)


class AssignCleaningTests(TestCase):
  def setUp(self):
    super().setUp()

    self.request_user = get_test_user()
    self.clean_co = get_test_work_co(owner=self.request_user)
    self.properly_rental = get_test_properly_rental(clean_co=self.clean_co)
    self.cleaning_config = get_test_cleaning_config(
        properly_rental=self.properly_rental)
    self.cleaning = get_test_cleaning(
        cleaning_config=self.cleaning_config,
        rental=self.properly_rental.rental,
        check_in=str_to_tz_dt('2019-01-10 16:00'),
        check_out=str_to_tz_dt('2019-01-11 11:00'))
    self.original_worker = get_test_work_co_worker(
        work_co=self.clean_co, name='Original Stu')
    self.new_worker = get_test_work_co_worker(
        work_co=self.clean_co, name='New Margy')
    self.assertFalse(explain_why_cant_assign_cleaning_to(
        self.request_user, self.cleaning, self.original_worker))
    self.api = Mock(spec=API)
    create_data = copy.deepcopy(CREATE_JOB)
    create_data['jobRequest.create'][0]['jobRequestId'] = 'heyoooo'
    self.api.job_request_create.return_value = create_data
    assign_cleaning_to(
        self.request_user, self.cleaning, self.original_worker,
        nnow=str_to_tz_dt('2019-01-07 16:00'), api=self.api)
    self.assertFalse(explain_why_cant_assign_cleaning_to(
        self.request_user, self.cleaning, self.new_worker))

  def test_why_not_inactive(self):
    self.new_worker.active = False
    self.new_worker.save()
    self.assertTrue(explain_why_cant_assign_cleaning_to(
        self.request_user, self.cleaning, self.new_worker))

  def test_why_not_non_owner(self):
    self.assertTrue(explain_why_cant_assign_cleaning_to(
        get_test_user(username='checkmate'),
        self.cleaning, self.new_worker))

  def test_why_not_wrong_owner(self):
    # The cleaning company changed.
    self.properly_rental.clean_co = get_test_work_co()
    self.properly_rental.save()
    self.cleaning.refresh_from_db()
    # But since a cleaner from the old company is still assigned the job, this
    # job is still the original cleaning company's responsibility.
    self.assertFalse(explain_why_cant_assign_cleaning_to(
        self.request_user, self.cleaning, self.new_worker))
    # Now that nobody is assigned the job, it's the new cleaning company's.
    self.cleaning.offered_to.set([])
    self.cleaning.accepted_by = None
    self.cleaning.save()
    self.assertTrue(explain_why_cant_assign_cleaning_to(
        self.request_user, self.cleaning, self.new_worker))

  def test_why_not_independent_cleaners(self):
    self.properly_rental.clean_co = None
    self.properly_rental.save()
    self.cleaning.offered_to.set([])
    self.cleaning.accepted_by = None
    self.cleaning.save()
    self.assertTrue(explain_why_cant_assign_cleaning_to(
        self.request_user, self.cleaning, self.new_worker))

  def test_why_not_cleaner_works_for_somebody_else(self):
    self.new_worker.work_co = get_test_work_co()
    self.new_worker.save()
    self.assertTrue(explain_why_cant_assign_cleaning_to(
        self.request_user, self.cleaning, self.new_worker))

  def test_why_not_completed(self):
    self.cleaning.completed_at = str_to_tz_dt('2019-01-01')
    self.cleaning.save()
    self.assertTrue(explain_why_cant_assign_cleaning_to(
        self.request_user, self.cleaning, self.new_worker))

  def test_why_not_canceled(self):
    self.cleaning.canceled_at = str_to_tz_dt('2019-01-01')
    self.cleaning.save()
    self.assertTrue(explain_why_cant_assign_cleaning_to(
        self.request_user, self.cleaning, self.new_worker))

  def test_assign_offered(self):
    assign_cleaning_to(
        self.request_user, self.cleaning, self.new_worker, self.api,
        str_to_tz_dt('2019-01-07 17:00'))
    self.assertEqual(1, self.cleaning.offered_to.count())
    self.assertEqual(
        self.new_worker,
        self.cleaning.offered_to.first().get_child_class_instance())

  def test_assign_accepted(self):
    # This test basically covers started as well.
    self.cleaning.accepted_by = self.original_worker
    self.cleaning.save()
    self.api.job_request_create.return_value = CREATE_JOB

    assign_cleaning_to(
        self.request_user, self.cleaning, self.new_worker, self.api,
        str_to_tz_dt('2019-01-07 17:00'))

    self.assertEqual(1, self.cleaning.offered_to.count())
    self.assertEqual(
        self.new_worker,
        self.cleaning.offered_to.first().get_child_class_instance())


class AssignCleaningsTableTests(TestCase):
  def setUp(self):
    super().setUp()
    request_user = get_test_user()
    self.clean_co = get_test_work_co(
        owner=request_user, services_tax_rate=5,
        name='Bobby Slobbys Cleaning Corporation')
    rental = get_test_rental(nickname='Bobs Burgers')
    properly_rental = get_test_properly_rental(
        clean_co=self.clean_co, rental=rental,
        cleaning_flat_rate=Money('87', 'USD'))
    get_test_cleaning_config(properly_rental=properly_rental)
    self.worker = get_test_work_co_worker(
        work_co=self.clean_co, name='Original Stu')
    self.jan_21 = get_test_cleaning(
        rental=rental, full_name='Steven Universe',
        check_in=str_to_tz_dt('2019-01-20 16:00'),
        check_out=str_to_tz_dt('2019-01-21 11:00'))
    # This is for a rental that's no longer assigned to this cleaning company,
    # but apparently it used to be assigned to this cleaning company because it
    # was accepted by somebody who works for this cleaning company.
    other_rental = get_test_rental(nickname='Mos Tavern')
    other_properly_rental = get_test_properly_rental(
        rental=other_rental, cleaning_flat_rate=Money('200', 'USD'))
    get_test_cleaning_config(
        properly_rental=other_properly_rental,
        cleaning_checklist=get_test_cleaning_checklist())
    self.jan_11 = get_test_cleaning(
        rental=other_rental, full_name='Rick Sanchez',
        check_in=str_to_tz_dt('2019-01-10 16:00'),
        check_out=str_to_tz_dt('2019-01-11 11:00'),
        offered_to=[self.worker], accepted_by=self.worker,
        completed_at=str_to_tz_dt('2019-01-11 13:00'),
        reviewed_by=get_test_user(username='Rachael Review', email='r@r.r'),
        reviewed_at=str_to_tz_dt('2019-01-11 15:00'))
    self.jan_11.workpayment.paypal_payout = get_successful_payout(
        amount=self.jan_11.workpayment.get_total_amount())
    self.jan_11.workpayment.save()
    get_test_did_slide(cleaning=self.jan_11)
    # This will only show up in clean queen. It's an unassigned cleaning for a
    # rental that's not configured for this cleaning company. However, since
    # this is the next reservation at other_rental, this check_in will show up
    # in the 'Next checkin' column for Rick Sanchez's cleaning.
    get_test_cleaning(
        rental=other_rental, full_name='Homer Simpson',
        check_in=str_to_tz_dt('2019-01-12 16:00'),
        check_out=str_to_tz_dt('2019-01-28 11:00'))
    # Shouldn't show up. No point. They never assigned a cleaner, so they
    # probably never even saw this cleaning.
    get_test_cleaning(
        rental=rental,
        check_in=str_to_tz_dt('2019-01-03 16:00'),
        check_out=str_to_tz_dt('2019-01-04 11:00'),
        canceled_at=str_to_tz_dt('2019-01-03'), offered_to=[])
    # Shouldn't show up. This rental obviously used to be done by independent
    # cleaners and one of them accepted it already.
    indep = get_test_independent_worker()
    get_test_cleaning(
        rental=rental,
        check_in=str_to_tz_dt('2019-01-03 16:00'),
        check_out=str_to_tz_dt('2019-01-04 11:00'),
        offered_to=[indep],
        accepted_by=indep)
    # Shouldn't show up. This rental obviously used to be done by a different
    # cleaning company and they assigned it and it was accepted already.
    other_clean_co_worker = get_test_work_co_worker(work_co=get_test_work_co(
        name='Totally unrelated cleaning company'))
    get_test_cleaning(
        rental=rental,
        check_in=str_to_tz_dt('2019-01-03 16:00'),
        check_out=str_to_tz_dt('2019-01-04 11:00'),
        offered_to=[other_clean_co_worker], accepted_by=other_clean_co_worker)
    # Also shouldn't show up because it's assigned to an independent worker.
    indep_worker = get_test_independent_worker()
    get_test_cleaning(
        rental=rental,
        check_in=str_to_tz_dt('2019-01-03 16:00'),
        check_out=str_to_tz_dt('2019-01-04 11:00'),
        offered_to=[indep_worker], accepted_by=indep_worker)
    # But this should show up because they assigned a cleaner so let's try to
    # make sure they see that it was canceled.
    self.jan_6 = get_test_cleaning(
        rental=rental, full_name='Princess Bubblegum',
        check_in=str_to_tz_dt('2019-01-05 16:00'),
        check_out=str_to_tz_dt('2019-01-06 11:00'),
        canceled_at=str_to_tz_dt('2019-01-03'),
        offered_to=[self.worker])

  def test_queen_clean(self):
    table = assign_cleanings_table(None, date(2019, 1, 1), date(2019, 2, 1))
    self.assertEqual('Mos Tavern', table.rows[0].cells[2])
    cleaner_cell = Cell(
        classes=['assignable'],
        additional_attrs={'data-editable-cleaner': 'true'})
    table.rows[1].assertEqual(Row([
        self._get_action_cell(self.jan_21, True), date(2019, 1, 21),
        'Bobs Burgers', '1 night', cleaner_cell,
        CREATED, None, None, Cell(), Cell(), None, None,
        'Bobby Slobbys Cleaning Corporation']))

  def test_my_cleanings_table(self):
    table = my_cleanings_table(self.worker, date(2019, 1, 1), date(2019, 2, 1))
    table.rows[0].assertEqual(Row([
        self._get_action_cell(self.jan_11, False), date(2019, 1, 11),
        'Mos Tavern', '1 night', 'PAID', str_to_tz_dt('2019-01-12 16:00'),
        'Homer Simpson', 'Rachael Review r@r.r',
        str_to_tz_dt('2019-01-11 15:00')]))

  def test_assign_cleanings_table(self):
    table = assign_cleanings_table(
        self.clean_co, date(2019, 1, 1), date(2019, 2, 1))
    edit_header = Cell(
        html_content='Action', csv_content='Cleaning ID', is_header=True)
    self.assertEqual([
        edit_header, 'Date', 'Unit', 'Length of stay', 'Cleaner', 'Status',
        'Next checkin', 'Next guest', 'Total amount', 'Invoice', 'Reviewed by',
        'Reviewed at'], table.headers)
    self.assertEqual(3, len(table.rows))

    cleaner_cell = Cell(
        classes=['assignable'], additional_attrs={
            'data-editable-cleaner': 'true'})
    table.rows[0].assertEqual(Row([
        self._get_action_cell(self.jan_21, True), date(2019, 1, 21),
        'Bobs Burgers', '1 night', cleaner_cell,
        CREATED, None, None, Cell(), Cell(), None, None]))
    worker_cell = Cell(
        content='Original Stu', classes=['assignable'], additional_attrs={
            'data-cleaner-id': self.worker.pk})
    invoice_cell = Cell(
        'cl{}'.format(self.jan_11.workpayment.pk),
        url='/invoice/{}/'.format(self.jan_11.workpayment.pk))
    # You can't edit a paid cleaning. $210 = 200 + 200 * .05 tax rate
    table.rows[1].assertEqual(Row([
        self._get_action_cell(self.jan_11, show_edit=False, show_review=True),
        date(2019, 1, 11), 'Mos Tavern', '1 night', worker_cell, 'PAID',
        str_to_tz_dt('2019-01-12 16:00'), 'Homer Simpson',
        Cell(Money('210', 'USD')), invoice_cell, 'Rachael Review r@r.r',
        str_to_tz_dt('2019-01-11 15:00')]))
    # Canceled cleanings have no start time really and therefore no following
    # reservation.
    table.rows[2].assertEqual(Row([
        self._get_action_cell(self.jan_6, True), date(2019, 1, 6),
        'Bobs Burgers', '1 night', worker_cell, 'CANCELED', None, None, Cell(),
        Cell(), None, None]))

  def _get_action_cell(self, cleaning, show_edit, show_review=False):
    html_content = ''
    if show_edit:
      html_content += (
          '<a href="/clean_co_cleaning/{}/" class="button">Edit</a>'.format(
              cleaning.pk))
    if show_review:
      html_content += (
          '<a href="/review_cleaning/{}/" class="button">Review</a>'.format(
              cleaning.pk))
    return Cell(
        html_content=html_content, csv_content=cleaning.pk,
        classes=['actions'])


class CleanCoCleaningTests(TestCase):
  def setUp(self):
    super().setUp()

    request_user = get_test_user()
    self.clean_co = get_test_work_co(
        owner=request_user, alerts_email='alert@clean.co')
    self.rental = get_test_rental(nickname='Bobs Burgers')
    properly_rental = get_test_properly_rental(
        clean_co=self.clean_co, rental=self.rental)
    get_test_cleaning_config(properly_rental=properly_rental)
    self.worker = get_test_work_co_worker(
        work_co=self.clean_co, name='Original Stu', worker_id='orig_stu_id',
        email='original@stu.stu')
    self.res = get_test_reservation(
        check_in=str_to_tz_dt('2019-01-10 16:00'),
        check_out=str_to_tz_dt('2019-01-16 11:00'),
        rental=self.rental, id_verified=True)
    self.assertEqual(
        'The cleaning time is more than 14 days away',
        Cleaning.objects.explain_why_cant_create_cleanings_in_keys(
            self.res, nnow=str_to_tz_dt('2019-01-02 11:14')))
    self.assertFalse(
        Cleaning.objects.explain_why_cant_create_cleanings_in_keys(
            self.res, nnow=str_to_tz_dt('2019-01-02 11:15')))
    self.api = Mock(spec=API)
    self.api.job_request_create.return_value = CREATE_JOB
    self.api.booking_create.return_value = BOOKING_CREATE
    Cleaning.objects.create_in_keys(
        nnow=str_to_tz_dt('2019-01-02 11:15'), api=self.api)
    self.cleaning = Cleaning.objects.get(
        rental=self.rental, job_request_id='',
        offered_start_time=str_to_tz_dt('2019-01-16 11:15'))
    self.assertTrue(self.cleaning.uses_work_co())
    self.cleaning.offered_to.set([self.worker])

    self.message_sender = Mock(spec=MessageSender)

  def test_checkout_changes_to_earlier_in_the_day(self):
    """ True story. """
    self.res.set_check_out(
        str_to_tz_dt('2019-01-14 11:00'),
        nnow=str_to_tz_dt('2019-01-14 17:00'))
    post_sync.send(
        sender=Reservation, instance=self.res, api=self.api,
        nnow=str_to_tz_dt('2019-01-14 17:00'),
        message_sender=self.message_sender)
    self.cleaning.refresh_from_db()
    self.assertEqual([], list(self.cleaning.offered_to.all()))
    self.assertEqual(
        str_to_tz_dt('2019-01-15 11:15'), self.cleaning.offered_start_time)
    message = Message.objects.get(
        reason=CHECKOUT_TIME_CHANGED_SO_REASSIGN, to='alert@clean.co')
    self.assertEqual([call(message)], self.message_sender.send.call_args_list)

  def test_checkout_changes_to_later(self):
    self.res.set_check_out(
        str_to_tz_dt('2019-01-17 11:00'),
        nnow=str_to_tz_dt('2019-01-09 12:00'))
    post_sync.send(
        sender=Reservation, instance=self.res, api=self.api,
        nnow=str_to_tz_dt('2019-01-09 12:00'),
        message_sender=self.message_sender)
    self.cleaning.refresh_from_db()
    self.assertEqual([], list(self.cleaning.offered_to.all()))
    self.assertEqual(
        str_to_tz_dt('2019-01-17 11:15'), self.cleaning.offered_start_time)
    message = Message.objects.get(
        reason=CHECKOUT_TIME_CHANGED_SO_REASSIGN, to='alert@clean.co')
    self.assertEqual([call(message)], self.message_sender.send.call_args_list)

  def test_rental_changes(self):
    # Everything normal
    self.assertEqual(1, self.res.cleaning_set.count())
    self.cleaning.accepted_by = self.worker
    self.cleaning.save()

    # The rental changes!
    new_rental = get_test_rental(nickname='Daves Dosas')
    get_test_cleaning_config(properly_rental=get_test_properly_rental(
        clean_co=self.clean_co, rental=new_rental))
    self.res.rental = new_rental
    self.res.save()
    post_sync.send(
        sender=Reservation, instance=self.res, api=self.api,
        nnow=str_to_tz_dt('2019-01-12 17:00'),
        message_sender=self.message_sender)

    # The existing cleaning simply changes rentals.
    self.cleaning.refresh_from_db()
    self.assertEqual(new_rental, self.cleaning.rental)

    self.assertEqual(2, self.res.cleaning_set.count())
    self.res.cleaning_set.get(
        offered_start_time=str_to_tz_dt('2019-01-16 11:15'), rental=new_rental,
        accepted_by=self.worker, reservation=self.res,
        canceled_at__isnull=True)
    # But there's a new cleaning at the old rental ASAP after the change
    self.res.cleaning_set.get(
        offered_start_time=str_to_tz_dt('2019-01-13 11:15'),
        rental=self.rental, accepted_by=None, reservation=self.res,
        canceled_at__isnull=True)

  def test_declined_by_service_provider_alerts(self):
    self.cleaning.job_request_id = 'resurrectionist'
    self.cleaning.save()
    declined_by = copy.deepcopy(DECLINED_BY_WORKER)

    # Properly completely changed the field names one time.
    zero = declined_by['results'][0]
    if not zero['jobRequestId']:
      raise Exception()
    if not zero['serviceProvider']:
      raise Exception()
    declined_by['results'][0]['jobRequestId'] = 'resurrectionist'
    declined_by['results'][0]['serviceProvider'] = 'original@stu.stu'

    email_sender = Mock(spec=EmailSender)
    message_sender = MessageSender(email_sender=email_sender)

    RawEvent.objects.create(json=json.dumps(declined_by)).handle(
        nnow=str_to_tz_dt('2019-01-11'), message_sender=message_sender)

    self.cleaning.refresh_from_db()
    self.assertEqual([], list(self.cleaning.offered_to.all()))
    self.assertEqual(CREATED, self.cleaning.status())
    Message.objects.get(
        to='alert@clean.co', reason=CLEAN_CO_CLEANING_NEEDS_CLEANER_ASAP)
    self.assertEqual(1, len(email_sender.send_mail.call_args_list))
    self.assertEqual(0, self.cleaning.offered_to.count())
    self.assertIsNone(self.cleaning.accepted_by)

  def test_canceled_by_service_provider_alerts(self):
    self.cleaning.accepted_by = self.worker
    self.cleaning.job_request_id = 'resurrectionist'
    self.cleaning.save()
    canceled_by = copy.deepcopy(CANCELED_BY_CLEANER)
    canceled_by['results'][0]['jobRequestId'] = 'resurrectionist'
    email_sender = Mock(spec=EmailSender)
    message_sender = MessageSender(email_sender=email_sender)

    RawEvent.objects.create(json=json.dumps(canceled_by)).handle(
        nnow=str_to_tz_dt('2019-01-07'), message_sender=message_sender)

    self.cleaning.refresh_from_db()
    # Used to set the status to CANCELED, but then I realized the cleanings
    # needed to get reopened so they can go through the workflow again.
    self.assertEqual(CREATED, self.cleaning.status())
    Message.objects.get(
        to='alert@clean.co', reason=CLEAN_CO_CLEANING_NEEDS_CLEANER_ASAP)
    self.assertEqual(1, len(email_sender.send_mail.call_args_list))
    self.assertEqual(0, self.cleaning.offered_to.count())
    self.assertIsNone(self.cleaning.accepted_by)


class SaveWorkerTests(TestCase):
  def setUp(self):
    super().setUp()
    WorkType.objects.create_work_types()
    self.post = {
        'name': 'Bobbery', 'phone': '987-6543', 'email': 'bill@bobbery.boing'}
    self.clean_co = get_test_work_co()

  def test_save_new(self):
    message_sender = Mock(spec=MessageSender)
    handle_cleaner_save(
        self.post, None, self.clean_co, message_sender=message_sender)
    worker = WorkCoWorker.objects.get(
        name='Bobbery', phone='987-6543', email='bill@bobbery.boing',
        work_types__name='Cleaner', active=False)
    message = Message.objects.get(
        to=settings.ALERT_NEW_CLEAN_CO_WORKER, reason=NEW_CLEAN_CO_WORKER)
    self.assertEqual([call(message)], message_sender.send.call_args_list)

    self.client.force_login(self.clean_co.owner)
    self.assert_get_contains(reverse('cleaners'), 'Bobbery')
    self.assert_get_contains(reverse('cleaner', args=(worker.pk,)), 'Bobbery')

  def test_save_existing(self):
    worker = get_test_work_co_worker(active=False)
    handle_cleaner_save(self.post, worker.pk, self.clean_co)
    worker.refresh_from_db()
    self.assertEqual('Bobbery', worker.name)
    self.assertEqual('987-6543', worker.phone)
    self.assertEqual('bill@bobbery.boing', worker.email)
    worker.work_types.get(name='Cleaner')


class CurrentAndNextReservationLookups(TestCase):
  def setUp(self):
    super().setUp()
    self.rental_1 = get_test_rental()
    self.res_1_1 = get_test_reservation(
        rental=self.rental_1, check_in=str_to_tz_dt('2018-12-25 16:00'),
        check_out=str_to_tz_dt('2018-12-27 11:00'))
    get_test_cleaning(reservation=self.res_1_1)
    self.res_1_2 = get_test_reservation(
        rental=self.rental_1, check_in=str_to_tz_dt('2018-12-28 16:00'),
        check_out=str_to_tz_dt('2018-12-29 11:00'))
    get_test_cleaning(reservation=self.res_1_2)
    self.rental_2 = get_test_rental()
    self.res_2_1 = get_test_reservation(
        rental=self.rental_2, check_in=str_to_tz_dt('2019-01-01 16:00'),
        check_out=str_to_tz_dt('2019-01-02 11:00'))
    get_test_cleaning(reservation=self.res_2_1)

  def test_current_reservation_lookup(self):
    current = current_res_lookup(
        [self.rental_1, self.rental_2, get_test_rental()],
        nnow=str_to_tz_dt('2018-12-26 12:00'))
    self.assertEqual({self.rental_1: self.res_1_1}, current)

  def test_next_reservation_lookup(self):
    nxt = next_res_w_cleaning_lookup(
        [self.rental_1, self.rental_2, get_test_rental()],
        nnow=str_to_tz_dt('2018-12-26 12:00'))
    self.assertEqual(
        {self.rental_1: self.res_1_2, self.rental_2: self.res_2_1}, nxt)
