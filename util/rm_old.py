"""
The manager of any class that wants to periodically delete everything over
a month old should inherit from RmOldManager, and also get an entry in
util/management/commands/rm_old.py. The class itself should have a
created_at datetime field.
"""
from datetime import timedelta

from django.db import models
from django.utils.timezone import now


class RmOldManager(models.Manager):
  def rm_old(self, days_ago=31, verbose=False):
    when = now() - timedelta(days=days_ago)
    which = self.filter(created_at__lt=when)
    if verbose:
      print('Deleting {} {}.'.format(which.count(), str(self.model)))
    which.delete()
