from django.db import models

from rentals.models import Rental
from util.fields import OneToOneOrNoneField


class Location(models.Model):
  rental = OneToOneOrNoneField(Rental, on_delete=models.CASCADE)
  location_id = models.PositiveIntegerField(unique=True, help_text=(
      'What ID does netsuite use to refer to this rental?'))
