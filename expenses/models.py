from django.db import models


class BankTransaction(models.Model):
  when
  title
  amount


class LongBuildingExpense(models.Model):
  start_month
  month_count
  total_amount
  amortize
  building
  title
  bank_transaction


class BuildingExpense(models.Model):
  month
  amount
  amortize
  building
  title
  bank_transaction
  long_building_expense


class ReservationExpense(models.Model):
  amount
  reservation
  title
  bank_transaction
