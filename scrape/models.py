from decimal import Decimal

from django.db import models
from djmoney.models.fields import MoneyField


UNKNOWN = 'UNKNOWN'
NO_AVAILABILITY = 'NO_AVAILABILITY'
SOME_AVAILABILITY = 'SOME_AVAILABILITY'
ALL_AVAILABILITY = 'ALL_AVAILABILITY'

AVAILABILITY_CHOICES = (
    (UNKNOWN, UNKNOWN),
    (NO_AVAILABILITY, NO_AVAILABILITY),
    (SOME_AVAILABILITY, SOME_AVAILABILITY),
    (ALL_AVAILABILITY, ALL_AVAILABILITY))


class Room(models.Model):
  airbnb_id = models.PositiveIntegerField()
  city = models.CharField(max_length=100)
  availability = models.CharField(
      max_length=20, choices=AVAILABILITY_CHOICES, default=UNKNOWN)


class Stay(models.Model):
  """
  Between looked_up_on and last_seen_on, we should be able to piece
  together a timeline of what price the rental was posted at.
  """
  room = models.ForeignKey(Room, on_delete=models.CASCADE)
  start = models.DateField(help_text=(
      'When would the hypothetical reservation start?'))
  end = models.DateField(help_text=(
      'When would the hypothetical reservation end?'))
  looked_up_on = models.DateField(help_text=(
      'The first time we saw this price_per_night for this start and end.'),
      null=True)
  last_seen_on = models.DateField(help_text=(
      'The most recent time we saw this price_per_night for this start '
      'and end.'), null=True)
  price_per_night = MoneyField(
      decimal_places=2, default=Decimal('0.0'), default_currency='XYZ',
      max_digits=10)
