from datetime import timedelta

from django.db import models
from django.utils.timezone import now


class LongRequestManager(models.Manager):
  def rm_old(self, days_ago=31, verbose=False):
    """ Basically an exact copy of
    guest_messages.models.RawMandrillEventManager.rm_old """
    when = now() - timedelta(days=days_ago)
    which = self.filter(created_at__lt=when)
    if verbose:
      print('Deleting {} long requests.'.format(which.count()))
    which.delete()


class LongRequest(models.Model):
  path = models.CharField(max_length=300)
  duration = models.DecimalField(
      decimal_places=3, max_digits=10, help_text=('In seconds.'))
  method = models.CharField(max_length=10)
  variables = models.TextField(
      help_text='request.POST or request.GET, depending on the method')
  created_at = models.DateTimeField(auto_now_add=True, db_index=True)

  objects = LongRequestManager()

  class Meta:
    ordering = ('-created_at',)
