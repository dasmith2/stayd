from datetime import date

from djmoney.money import Money

from expenses.models.expenses import (
    Expense, ReservationExpense, DAYS_OF_THE_MONTH)
from rentals.tests import get_test_building
from reservations.tests import get_test_reservation


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


def get_test_reservation_expense(create, **kwargs):
  reservation = get_test_reservation(True, **kwargs)
  reservation_expense = ReservationExpense(
      amount=kwargs.get('amount', Money('10.0', 'USD')),
      reservation=kwargs.get('reservation', reservation),
      description=kwargs.get('description', 'Expense stuff'))
  if create:
    reservation_expense.save()
  return reservation_expense
