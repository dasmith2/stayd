from django.db import models


class RawEvent(models.Model):
  json = models.TextField()
  headers = models.TextField()
