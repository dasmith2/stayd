from datetime import date

from django.shortcuts import reverse

from work.models.pay_service_providers import (
    get_pay_service_provider_payments, WorkPayment)
from work.tests.test_cleaning import get_test_cleaning
from work.tests.test_message import get_test_message
from work.tests.test_raw_event import get_test_raw_event
from work.tests.test_rental import get_test_properly_rental
from work.tests.test_worker import get_test_independent_worker
from rentals.tests import get_test_building, get_test_rental
from util.tests import TestCase
from util.timezone import str_to_tz_dt


class ViewTests(TestCase):
  def test_cleaning_history(self):
    rental = get_test_rental(nickname='Colbys place')
    get_test_properly_rental(rental=rental)
    cleaning = get_test_cleaning(rental=rental)
    get_test_message(work=cleaning, subject='Hello Stu')
    get_test_raw_event(work=cleaning, event_name='blargh.underBlarghed')
    url = '/admin/work/cleaning/{}/change/'.format(cleaning.pk)

    self.login(is_superuser=True)

    got = self.get(url)
    self.assertTrue(got.find('Hello Stu') >= 0)
    self.assertTrue(got.find('blargh.underBlarghed') >= 0)

  def test_raw_event_list(self):
    cleaning = get_test_cleaning(nickname='Buckingham palace')
    get_test_raw_event(work=cleaning, event_name='blargh.underBlarghed')

    self.login(is_superuser=True)

    self.assert_get_contains('/admin/work/rawevent/', 'Buckingham palace')

  def test_missing_accepted_by_and_started_at(self):
    # One time we ended up with a job that was completed but didn't have an
    # accepted_by. You get that in the corner cases where a worker doesn't have
    # the correct worker_id. Another time we had a job with a completed_at, but
    # without a started_at. That happens when Properly fails to send us a job
    # started webhook and the sync_jobs function hasn't run in the meantime.
    building = get_test_building()
    rental = get_test_rental(nickname='Fatimas place', building=building)
    get_test_properly_rental(rental=rental)
    bob = get_test_independent_worker(buildings=[building])
    jane = get_test_independent_worker(buildings=[building])
    cleaning = get_test_cleaning(
        check_in=str_to_tz_dt('2019-01-01 16:00'),
        check_out=str_to_tz_dt('2019-01-02 11:00'),
        started_at=None,
        completed_at=str_to_tz_dt('2019-01-02 14:00'),
        accepted_by=None, offered_to=[bob, jane], rental=rental)
    self.assertTrue(cleaning.workpayment)
    WorkPayment.objects.filter(pk=cleaning.workpayment.pk).update(
        created_at=str_to_tz_dt('2019-01-02 14:00'))
    payments = get_pay_service_provider_payments(
        date(2019, 1, 1), date(2019, 2, 1))
    self.assertTrue(cleaning.workpayment in payments)

    self.login(is_superuser=True)
    date_kwargs = {
        'from_date_str': '01-01-2019', 'to_date_str': '02-01-2019'}

    history_url = reverse(
        'cleaning_history_detail', kwargs={'pk': cleaning.pk})
    self.assert_get_contains(history_url, 'Fatimas place')

    totals_url = reverse('pay_service_provider_totals', kwargs=date_kwargs)
    self.assert_get_contains(totals_url, '???')

    pay_url = reverse('pay_service_providers', kwargs=date_kwargs)
    self.assert_get_contains(pay_url, 'Fatimas place')
