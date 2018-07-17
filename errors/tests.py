import sys

from util.tests import TestCase

from errors.models import log_error, StaydError


class LogErrorTests(TestCase):
  def test_log_error(self):
    b = {}
    for i in range(2):
      try:
        b['hello!']
      except Exception:
        log_error(
            'a = b?!', 'here are some details', sys.exc_info())
    stayd_error = StaydError.objects.get(title='a = b?!')
    self.assertEqual(2, stayd_error.count)
    self.assertEqual(stayd_error.message, 'here are some details')
    self.assertEqual(
        stayd_error.error_message, 'KeyError(\'hello!\',)')
    self.assertTrue(bool(stayd_error.stack_trace))

    stayd_error.fixed = True
    stayd_error.save()

    try:
      b['hello!']
    except Exception:
      log_error(
          'a = b?!', 'here are some details', sys.exc_info())
    errors = StaydError.objects.filter(title='a = b?!').order_by('pk')
    self.assertEqual(2, errors.count())
    self.assertTrue(errors[0].fixed)
    self.assertFalse(errors[1].fixed)
