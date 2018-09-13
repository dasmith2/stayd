from django.db import models

from util.rm_old import RmOldManager


class LongRequest(models.Model):
  path = models.CharField(max_length=300)
  duration = models.DecimalField(
      decimal_places=3, max_digits=10, help_text=('In seconds.'))
  method = models.CharField(max_length=10)
  variables = models.TextField(
      help_text='request.POST or request.GET, depending on the method')
  created_at = models.DateTimeField(auto_now_add=True, db_index=True)

  objects = RmOldManager()

  class Meta:
    ordering = ('-created_at',)
