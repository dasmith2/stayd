from django.db import models

class Guest(models.Model):
  full_name = models.TextField(help_text=(
      'At the moment this is scraped verbatim off of Airbnb.'))
  joined_airbnb_when = models.DateField()
  airbnb_says_theyre_from = models.TextField()
  phone = models.CharField(max_length=50)
