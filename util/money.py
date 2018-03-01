import djmoney
import re


def number_only_format(money):
  return re.sub(r'[^\d\.]', '', djmoney.money.format_money(money))
