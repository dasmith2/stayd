from datetime import time
from django.utils import timezone


class Clock(object):
  def __init__(self):
    self.started_at = None

  def start(self):
    self.started_at = timezone.now()

  def elapsed_seconds(self):
    if not self.started_at:
      raise Exception(
          'You need to start() the clock before you can call elapsed_seconds')
    return (timezone.now() - self.started_at).seconds

  def sleep(self, seconds):
    time.sleep(seconds)

  def now(self):
    return timezone.now()
