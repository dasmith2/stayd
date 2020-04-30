from datetime import datetime
from django.conf import settings

from errors.models import StaydError
from performance.models import LongRequest


def TrackRequestTimeMiddleware(get_response):
  def middleware(request):
    start = datetime.now()
    response = get_response(request)
    duration_delta = datetime.now() - start
    duration_seconds = (
        duration_delta.seconds + duration_delta.microseconds / 1000000)
    if duration_seconds > settings.MAX_ALLOWED_REQUEST_TIME:
      method = request.method
      variables = None
      if method == 'GET':
        variables = request.GET
      elif method == 'POST':
        variables = request.POST
      LongRequest.objects.create(
          path=request.path, duration=duration_seconds, method=method,
          variables=variables)
    return response

  return middleware


class LogExceptionsMiddleware:
  def __init__(self, get_response):
    self.get_response = get_response

  def __call__(self, request):
    return self.get_response(request)

  def process_exception(self, request, exception):
    title = '{} at {}'.format(type(exception).__name__, request.path)
    message = ''
    # Just a quick and dirty reverse engineering of sys.exc_info() I do it this
    # way so the tests are valid.
    exc_info = (exception.__class__, exception, exception.__traceback__)
    extra_to = []
    always_new_error = False
    StaydError.objects.log_error(
        title, message, exc_info, extra_to, always_new_error)
