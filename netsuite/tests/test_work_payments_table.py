from datetime import date

from django.shortcuts import reverse
from djmoney.money import Money

from netsuite.models.work_payments_table import (
    payments_for_netsuite_work_table, netsuite_work_table)
from netsuite.tests.test_netsuite_class import get_test_rental_class
from util.permission import ACCOUNTANT
from util.table import Row
from util.urls import date_to_url_str
from work.tests.test_pay_service_providers import (
    PaymentExamplesTests, pay_my_payment_examples)


class PaymentsForNetsuiteWorkTableTests(PaymentExamplesTests):
  def test_payments_for_netsuite_work_table(self):
    self.assertEqual([], payments_for_netsuite_work_table(
        date(2018, 12, 1), date(2019, 1, 1)))
    pay_my_payment_examples(self)
    self.assertEqual(set([
        self.indep_work_payment,
        self.manual_payment,
        self.work_co_payment,
        self.one_off_payment]), set(payments_for_netsuite_work_table(
            date(2018, 12, 1), date(2019, 1, 1))))
    self.assertEqual([], payments_for_netsuite_work_table(
        date(2019, 1, 1), date(2019, 2, 1)))


class NetsuiteWorkTableTests(PaymentExamplesTests):
  def setUp(self):
    super().setUp()
    pay_my_payment_examples(self)
    get_test_rental_class(rental=self.work_co_rental, code=565)

  def test_view(self):
    self.login(group=ACCOUNTANT)
    url = reverse('netsuite_csv_worker_payments', kwargs={
        'from_date_str': date_to_url_str(date(2018, 12, 1)),
        'to_date_str': date_to_url_str(date(2019, 1, 1))})
    self.assert_get_contains(url, 'Fixed the couch')

  def test_clean_co_cleaning(self):
    invoice_no = self.work_co_payment.invoice_number()

    table = netsuite_work_table([self.work_co_payment])
    self.assertEqual(3, len(table.rows))
    table.rows[0].assertEqual(Row([
        invoice_no, invoice_no, 'Janes Cleaning Company', None,
        'Clean Co Workers apt 2', None, date(2018, 12, 24), None,
        date(2018, 12, 24),
        'a cleaning at Clean Co Workers apt 2 on 2018-12-24',
        None, None, None, None, None, 'Cleaning Services Expense', 926,
        Money('53', 'USD'), None, 565]))
    table.rows[1].assertEqual(Row([
        invoice_no, invoice_no, 'Janes Cleaning Company', None,
        'Clean Co Workers apt 2', None, date(2018, 12, 24), None,
        date(2018, 12, 24),
        'Fixed the couch',
        None, None, None, None, None, 'Cleaning Services Expense', 926,
        Money('10', 'USD'), None, 565]))
    table.rows[2].assertEqual(Row([
        invoice_no, invoice_no, 'Janes Cleaning Company', None,
        'Clean Co Workers apt 2', None, date(2018, 12, 24), None,
        date(2018, 12, 24),
        'Sales tax',
        None, None, None, None, None, 'Cleaning Services Expense', 926,
        Money('6.30', 'USD'), None, 565]))
