from datetime import date

from util.web_test import WebTest, WebTestCommand
from work.tests.test_pay_service_providers import (
    clean_up_my_payment_examples, set_my_payment_examples,
    pay_my_payment_examples)


class Command(WebTestCommand):
  help = (
      'Run this from your local machine to create a few payments and load '
      'the pay service providers page.')

  def web_test_classes(self):
    return [CleanCoExample]


class CleanCoExample(WebTest):
  def run(self):
    self.setup_test_payments()
    self.load_netsuite_csv()

  def setup_test_payments(self):
    clean_up_my_payment_examples(self)
    set_my_payment_examples(self)
    pay_my_payment_examples(self)
    set_my_payment_examples(self, offset_days=-5)
    pay_my_payment_examples(self)
    set_my_payment_examples(self, offset_days=-10)
    pay_my_payment_examples(self)

  def load_netsuite_csv(self):
    self.dated_report_get('netsuite_csv', date(2018, 12, 1), date(2019, 1, 1))
    self.login()
