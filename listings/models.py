from django.db import models
from rentals.models import Rental
from util.channels import CHANNEL_OPTIONS


class Listing(models.Model):
  """ This class is now totally defunct and should go away. """
  channel = models.CharField(choices=CHANNEL_OPTIONS, max_length=20)
  channel_listing_id = models.CharField(
      db_index=True, max_length=50, help_text=(
          'The id given to this listing by Airbnb, booking.com, or whomever.'))
  rental = models.ForeignKey(Rental, on_delete=models.CASCADE)

  def __str__(self):
    return '{}:{}'.format(self.channel, self.rental.airbnb_address_scrape)
