from datetime import date

from djmoney.money import Money

from expenses.models import Expense, DAYS_OF_THE_MONTH
from rentals.tests import get_test_building


def get_test_expense(create, **kwargs):
  building = None
  if 'building' not in kwargs and 'owner' not in kwargs:
    building = get_test_building(True, **kwargs)
  expense = Expense(
      month=kwargs.get('month', date(2018, 10, 1)),
      amount=kwargs.get('amount', Money('10.0', 'USD')),
      amortize=kwargs.get('amortize', DAYS_OF_THE_MONTH),
      building=kwargs.get('building', building),
      owner=kwargs.get('owner', None))
  if create:
    expense.save()
  return expense
