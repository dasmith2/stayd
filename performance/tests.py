from errors.models import StaydError
from performance.middleware import LogExceptionsMiddleware
from util.tests import TestCase


class FakeRequest:
  path = '/goof_off_day/'


class LogExceptionsMiddlewareTests(TestCase):
  def test_process_exception(self):
    exception = None
    try:
      layers = of['success']  # noqa:F841,F821
    except Exception as ex:
      exception = ex
    LogExceptionsMiddleware(None).process_exception(FakeRequest(), exception)
    error = StaydError.objects.get(title='NameError at /goof_off_day/')
    self.assertTrue(error.stack_trace.find('layers = of') > 0)
