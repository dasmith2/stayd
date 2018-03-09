from django.db import models
from places.models import Rental
from util.channels import CHANNELS

class Listing(models.Model):
  """ A listing is, like, the page on Airbnb you go to that shows you
  the room, shows you a calendar, and invites you to create a reservation. At
  the moment I hope we can reuse the same class here for listings on Airbnb,
  Booking.com, and so on. But be prepared to split it out. """
  channel = models.CharField(choices=CHANNELS, max_length=20)
  channel_listing_id = models.CharField(max_length=50, help_text=(
      'The id given to this listing by Airbnb, booking.com, or whomever.'))
  title = models.TextField(help_text=(
      'SPACIOUS 3BR/2BA **2 STOPS FROM NYC** SLEEPS10!!!'))
  rental = models.ForeignKey(Rental, on_delete=models.CASCADE)
  firefox_profile = models.TextField(null=True, help_text=(
      'This is the name of the firefox profile folder you use in order to '
      'login to airbnb to manage this listing. That profile should contain '
      'proxy login information and Airbnb login cookies.'))
