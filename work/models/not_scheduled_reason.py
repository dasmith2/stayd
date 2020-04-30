from django.conf import settings
from django.db import models


class NotScheduledReasonFinder(object):
  """ OK look, I know caches cause exceptions. But honestly these are very,
  very rarely going to change. I wouldn't have made an object at all except
  that I need to pass something in a query string to reference these because
  there's a filter on them on the tickets page. """
  def __init__(self):
    self.cache = None

  def by_name(self, name):
    # The database gets cleared after every test, invalidating the cache.
    if settings.TEST:
      self.cache = None
    if self.cache is None:
      self.cache = {}
      for reason in NotScheduledReason.objects.all():
        self.cache[reason.name] = reason
    if name not in self.cache:
      self.cache[name] = NotScheduledReason.objects.get_or_create(name=name)[0]
    return self.cache[name]


not_scheduled_reason_finder = NotScheduledReasonFinder()


class NotScheduledReason(models.Model):
  """ Why didn't a ticket get scheduled? """
  name = models.CharField(max_length=200)
