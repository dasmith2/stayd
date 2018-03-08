from django.db import models


class Host(models.Model):
  name = models.CharField(max_length=100, default='')


class Rental(models.Model):
  airbnb_address_scrape = models.TextField(help_text=(
      'This is the address as scraped off Airbnb verbatim. Just... '
      'hang onto this field to make our lives easier for now.'))
  accomodates = models.PositiveIntegerField(help_text=(
      'How many people can sleep here.'))
  bathrooms = models.PositiveIntegerField()
  bedrooms = models.PositiveIntegerField()
  property_type = models.CharField(max_length=50, help_text=(
      'Keep this vague until I know what the exhaustive enumeration '
      'of possible values is.'))
  room_type = models.CharField(max_length=50, help_text=(
      'Keep this vague until I know what the exhaustive enumeration '
      'of possible values is.'))
