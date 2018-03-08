from django.db import models
from places.models import Rental
from util.channels import CHANNELS

class Listing(models.Model):
  """ A listing is, like, the page on Airbnb you go to that shows you
  the room, shows you a calendar, and invites you to create a reservation. At
  the moment I hope we can reuse the same class here for listings on Airbnb,
  Booking.com, and so on. But be prepared to split it out. """
  channel = models.CharField(choices=CHANNELS)
  channel_listing_id = models.CharField(max_length=50, help_text=(
      'The id given to this listing by Airbnb, booking.com, or whomever.'))
  rental = models.ForeignKey(Rental, on_delete=models.CASCADE)
