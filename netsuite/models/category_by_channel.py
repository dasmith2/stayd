from django.db import models

from util.channels import CHANNELS


CHANNEL_CHOICES = [(channel, channel) for channel in CHANNELS]


class CategoryByChannel(models.Model):
  channel = models.CharField(
      max_length=100, choices=CHANNEL_CHOICES, unique=True)
  sales_category_name = models.CharField(max_length=100)
  sales_category_id = models.PositiveIntegerField()
  fee_category_name = models.CharField(max_length=100)
  fee_category_id = models.PositiveIntegerField()
