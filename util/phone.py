import re


def maybe_prepend_plus(phone):
  """ Itnl. phone numbers come in from Guesty, like, 'phone': '447465980244'
  But front treats '447465980244' and '+447465980244' as totally different
  numbers. Moreover, actual communication with the number goes in Front's
  system as the + version. """
  digit_count = len(re.sub(r'[^\d]', '', phone))
  if digit_count <= 10 or phone[0] == '+':
    return phone
  return '+{}'.format(phone)
