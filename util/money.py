import djmoney
import re


def number_only_format(m):
  return re.sub(r'[^\d\.]', '', djmoney.money.format_money(m))


def readable(num):
  """ A python version of readable in static/js/util.js """
  if num.__class__ is djmoney.money.Money:
    num = num.amount
  num = float(num)
  suffix_i = 0
  on_num = num
  while on_num > 1000:
    on_num = on_num / 1000.0
    suffix_i += 1
  display_num = round(on_num)
  if on_num < 10:
    display_num = round(on_num, 1)
  return '{}{}'.format(display_num, ['', 'K', 'M', 'B', 'T'][suffix_i])


def readable_money(num):
  return '${}'.format(readable(num))
