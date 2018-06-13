from django.db import models

from errors.models import StaydError


class CommandRun(models.Model):
  command_name = models.CharField(max_length=200)
  started = models.DateTimeField()
  completed = models.DateTimeField(null=True, blank=True)
  error = models.ForeignKey(
      StaydError, null=True, blank=True, on_delete=models.CASCADE)
