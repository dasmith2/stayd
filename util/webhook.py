""" Shared stuff for handling all the apis that send us webhooks. """
import json

from django.db import models
from django.http import HttpResponse


class Webhook(models.Model):
  json = models.TextField(help_text='The raw json string from the request.')
  created_at = models.DateTimeField(auto_now_add=True, db_index=True)
  handled_at = models.DateTimeField(null=True, blank=True)

  def as_html(self):
    data = json.loads(self.json)
    as_str = json.dumps(data, indent=2)
    return HttpResponse('<pre>{}</pre>'.format(as_str))

  def data(self):
    return json.loads(self.json)

  class Meta:
    abstract = True
