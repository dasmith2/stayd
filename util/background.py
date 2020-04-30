import sys

from django.conf import settings
from rq import Queue

from errors.models import log_error
from redis.connection import ResponseError
from worker import conn


# The default default_timeout is 2 minutes. This makes it an hour.
q = Queue(connection=conn, default_timeout=60 * 60)


def background(func):
  """ Put this decorator on functions you wanna run the in background.

  Don't, like,
  whatever(only_copy_of_my_data)

  @background
  def whatever(my_data):
    # You may never get here!

  Do more like
  my_data_id = store_data(only_copy_of_my_data)
  whatever(my_data_id)

  @background
  def whatever(my_data_id):
    my_data = get_data(my_data_id)

  There's a queue of data from the foreground to the background, and that
  queue only has so much memory. 5MB at this point, because that was free.
  This is more than enough memory if we're just pushing ids to the background.
  If you push real data through the queue you could a) use up all the memory
  and cause the queue to crash and b) now the only copy of your data is hung
  up in a crashed queue. I made that mistake at first by putting entire
  guesty webhooks in the argument of a @background function.

  You can see how much memory the queue is using by going to
  https://dashboard.heroku.com/apps/stayd-prod and clicking on "Redis To Go".
  It should be less than 10%.

  If redis does run out of memory, then hopefully a bunch of error handling I
  put in place will help with that. The only answer I've worked out to that
  situation is

  heroku addons:destroy redistogo -a stayd-prod
  heroku addons:create redistogo:nano -a stayd-prod
  heroku restart -a stayd-prod

  Obviously that throws out all data that was hung up in Redis.

  Unfortunately you can NOT decorate manager functions, like,
  class FooManager(models.Manager):
    @background
    def task(self):
      whatever

  because when you do Foo.objects.task() this wrapper will have closed
  around, like, foos.models.task which doesn't actually exist. Unfortunately!
  I have not worked out how to catch and notify of this error!! This is
  definitely a crack that errors can and do fall through!

  There are a bunch of comments in worker.py for how to debug what's happening
  with the background queue.

  I think it's a bad idea to do, like,
  @background
  def whatever(**kwargs):

  because then rq.job can throw "can't pickle weakref objects" and you have no
  idea what in kwargs is causing the problem.
  """
  def func_wrapper(*args, **kwargs):
    if settings.TEST or settings.DEBUG:
      # In a test environment we just wanna run everything synchronously
      # so just run the function right away. We should get these tasks
      # running in a local environment, but for the time being, just run
      # those synchronously as well.
      func(*args, **kwargs)
    elif settings.BACKGROUND or settings.SHELL:
      # If we're in the background we wanna run the function, but we need
      # some kind of error reporting mechanism.
      try:
        func(*args, **kwargs)
      except Exception:
        log_error('{} error'.format(func.__name__), exc_info=sys.exc_info())
    else:
      # Otherwise we're on web or something and we wanna kick this function
      # off to a background thread.
      try:
        q.enqueue(func, *args, **kwargs)
      except Exception as ex:
        search_for = "OOM command not allowed when used memory > 'maxmemory'"
        is_response_error = isinstance(ex, ResponseError)
        if is_response_error and ex.args[0].find(search_for) >= 0:
          message = (
              'I fixed this one time by running\n'
              'heroku addons:destroy redistogo -a stayd-prod\n'
              'heroku addons:create redistogo:nano -a stayd-prod\n'
              'heroku restart -a stayd-prod')
          log_error('Redis is out of memory', message, sys.exc_info())
        else:
          log_error(
              'Unknown error enquing background task', func.__name__,
              sys.exc_info())

  return func_wrapper
