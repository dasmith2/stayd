from django.db import models

from util.rm_old import RmOldManager


class RawEvent(models.Model):
  json = models.TextField(help_text='The raw json string from the request.')
  created_at = models.DateTimeField(auto_now_add=True, db_index=True)
  handled_at = models.DateTimeField(null=True, blank=True)

  objects = RmOldManager()
