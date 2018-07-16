from rq import Queue
import sys

from django.conf import settings

from errors.models import log_error
from worker import conn


q = Queue(connection=conn)


def background(func):
  """ Put this decorator on functions you wanna run the in background. """
  def func_wrapper(*args, **kwargs):
    if settings.TEST:
      # In a test environment we just wanna run everything synchronously
      # so just run the function right away.
      func(*args, **kwargs)
    elif settings.BACKGROUND:
      # If we're in the background we wanna run the function, but we need
      # some kind of error reporting mechanism.
      try:
        func(*args, **kwargs)
      except Exception:
        log_error('{} error'.format(func.__name__), exc_info=sys.exc_info())
    else:
      # Otherwise we're on web or something and we wanna kick this function
      # off to a background thread.
      q.enqueue(func, *args, **kwargs)
  return func_wrapper
