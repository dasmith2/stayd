import re


def numbers_only(number_str):
  if number_str.__class__ is int:
    return str(number_str)
  return re.compile(r'[^\d]').sub('', number_str)


def looks_like_phone_number(phone):
  return _digit_count(phone) >= 9


def maybe_prepend_plus(phone):
  """ Itnl. phone numbers come in from Guesty, like, 'phone': '447465980244'
  But front treats '447465980244' and '+447465980244' as totally different
  numbers. Moreover, actual communication with the number goes in Front's
  system as the + version. """
  if _digit_count(phone) <= 10 or phone[0] == '+':
    return phone
  return '+{}'.format(phone)


def _digit_count(phone):
  return len(re.sub(r'[^\d]', '', phone))
