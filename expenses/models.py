from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models

from djmoney.models.fields import MoneyField

from rentals.models import Building
from reservations.models import Reservation


class BankTransaction(models.Model):
  when = models.DateField(db_index=True)
  description = models.TextField()
  amount = MoneyField(
      max_digits=10, decimal_places=2, default_currency='USD')


DAYS_OF_THE_MONTH = 'days of the month'  # For instance, the 28 days of Feb.
AVAILABLE_NIGHTS = 'available nights'  # 2 units? 56 available nights in Feb.
BOOKED_NIGHTS = 'booked nights'  # Depends on reserations.
AMORTIZE_CHOICES = (
    (DAYS_OF_THE_MONTH, DAYS_OF_THE_MONTH),
    (AVAILABLE_NIGHTS, AVAILABLE_NIGHTS),
    (BOOKED_NIGHTS, BOOKED_NIGHTS))


class ExpenseBase(models.Model):
  amortize = models.CharField(
      choices=AMORTIZE_CHOICES, max_length=20, help_text=(
          'No expense counts towards a single day. They get split evenly '
          'between things.'))
  building = models.ForeignKey(
      Building, on_delete=models.CASCADE, null=True, blank=True)
  owner = models.ForeignKey(
      User, on_delete=models.CASCADE, null=True, blank=True)
  description = models.TextField()
  bank_transaction = models.ForeignKey(
      BankTransaction, on_delete=models.CASCADE, null=True, blank=True)

  def clean(self):
    if bool(self.owner) == bool(self.building):
      raise ValidationError('Set exactly one of owner and building.')


class LongExpense(ExpenseBase):
  start_month = models.DateField(help_text='Starting on this month...')
  month_count = models.PositiveIntegerField(
      help_text='And for this many months...')
  total_amount = MoneyField(
      max_digits=10, decimal_places=2, default_currency='USD', help_text=(
          'Split this total amount evenly between those months.'))


class Expense(ExpenseBase):
  month = models.DateField(
      db_index=True, help_text='What month does this expense apply to?')
  amount = MoneyField(
      max_digits=10, decimal_places=2, default_currency='USD', help_text=(
          'How much was this expense? Or at least, how much of the original '
          'expense counts towards this particular month from the original '
          'long_expense?'))
  long_expense = models.ForeignKey(
      LongExpense, null=True, blank=True, help_text=(
          'This expense may be just a fraction of a one time larger expense '
          'that got split between a few months.'))

  def clean(self):
    super().clean()
    if bool(self.long_expense) and bool(self.bank_transaction):
      raise ValidationError(
          'The bank transaction should only be stored with the LongExpense')


class ReservationExpense(models.Model):
  amount = MoneyField(
      max_digits=10, decimal_places=2, default_currency='USD')
  reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE)
  description = models.TextField()
  bank_transaction = models.ForeignKey(
      BankTransaction, on_delete=models.CASCADE, null=True, blank=True)
