import sys

from django.conf import settings
from rq import Queue

from errors.models import log_error
from worker import conn


# The default default_timeout is 2 minutes. This makes it an hour.
q = Queue(connection=conn, default_timeout=60 * 60)


def background(func):
  """ Put this decorator on functions you wanna run the in background.

  Unfortunately you can NOT decorate manager functions, like,
  class FooManager(models.Manager):
    @background
    def task(self):
      whatever

  because when you do Foo.objects.task() this wrapper will have closed
  around, like, foos.models.task which doesn't actually exist. """
  def func_wrapper(*args, **kwargs):
    if settings.TEST or settings.DEBUG:
      # In a test environment we just wanna run everything synchronously
      # so just run the function right away. We should get these tasks
      # running in a local environment, but for the time being, just run
      # those synchronously as well.
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
