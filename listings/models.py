from django.db import models
from rentals.models import Rental
from util.channels import CHANNELS


class Airvatar(models.Model):
  """ Airbnb Avatar. These exist to mitigate the risk of Airbnb shutting down
  a host. We don't want a shutdown of any one particular
  Airbnb login to affect business as usual too dramatically. So to manage
  1000 properties, we'll make 200 or so separate Airbnb logins, each 'managing'
  5 or so listings. These are those logins. It should be basically impossible
  for Airbnb to tie any one Airvatar to any other. So every Airvatar gets its
  own IP address via a proxy, for instance. """
  name = models.TextField(help_text=(
      'This should be a human name, but not for an actual human. Once a name '
      'is in motion, it shouldn\'t be changed.'), unique=True)
  name_slug = models.SlugField(max_length=100, null=True, help_text=(
      'Just let the Django admin fill this in automatically.'))
  ip = models.CharField(max_length=50, help_text=(
      'Each Airvatar gets its own IP address. These should be purchased as '
      'proxies and painstakingly entered here. You can\'t just make up an IP '
      'address. All web traffic from this Airvatar will appear to come '
      'from this IP address.'))
  port = models.PositiveIntegerField(help_text=(
      'Proxies have ips and ports.'))
  gmail_address = models.TextField(help_text=(
      'This will also serve as the Airbnb username/email.'))
  gmail_password = models.CharField(max_length=20)
  airbnb_password = models.CharField(max_length=20)

  def __str__(self):
    return self.name

  class Meta:
    ordering = ('name',)


class Listing(models.Model):
  """ A listing is, like, the page on Airbnb you go to that shows you
  the room, shows you a calendar, and invites you to create a reservation. At
  the moment I hope we can reuse the same class here for listings on Airbnb,
  Booking.com, and so on. But be prepared to split it out. """
  channel = models.CharField(choices=CHANNELS, max_length=20)
  channel_listing_id = models.CharField(
      db_index=True, max_length=50, help_text=(
          'The id given to this listing by Airbnb, booking.com, or whomever.'))
  airvatar = models.ForeignKey(Airvatar, null=True, help_text=(
      'Basically, who do you need to log in as in order to manage this '
      'listing.'), on_delete=models.CASCADE)
  title = models.TextField(help_text=(
      'SPACIOUS 3BR/2BA **2 STOPS FROM NYC** SLEEPS10!!!'))
  rental = models.ForeignKey(Rental, on_delete=models.CASCADE)

  def airvatar_name(self):
    """ Mainly for the benefit of the serializer. """
    return self.airvatar.name

  def __str__(self):
    return '{}:{}'.format(self.channel, self.rental.airbnb_address_scrape)
