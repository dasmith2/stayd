from datetime import datetime

from django.conf import settings

from performance.models import LongRequest
from util.background import background


@background
def track_request(path, full_path, duration, method, variables):
  LongRequest.objects.create(
      path=path, duration=duration, method=method, variables=variables)


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
      path = request.path
      full_path = request.get_full_path()
      track_request(path, full_path, duration_seconds, method, variables)
    return response

  return middleware
