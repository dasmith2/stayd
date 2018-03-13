import djmoney
import moneyed
import re


def number_only_format(m):
  return re.sub(r'[^\d\.]', '', djmoney.money.format_money(m))


def money_needs_currency(m):
  return m.__class__ is not djmoney.m.Money \
      or m.currency == moneyed.CURRENCIES['XYZ']
