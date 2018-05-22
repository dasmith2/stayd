import moneyed
import pytz
from djmoney.money import Money
from django.db import models
from django.utils.timezone import make_aware, is_aware

from pays.models import Payable


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
  front_channel = models.CharField(
      max_length=100, null=True, blank=True, help_text=(
          'This is no longer necessary. It was mistakenly put in place '
          'for guest messages, but they all use settings.FRONT_SMS_CHANNEL_ID '
          'now.'))

  def __str__(self):
    return self.name

  class Meta:
    ordering = ('name',)


class Owner(Payable):
  """ Somebody who, for our purposes anyway, owns properties and will want
  to get paid for reservations. """
  name = models.CharField(max_length=100, default='')

  def __str__(self):
    return self.name


class Rental(models.Model):
  """ A rental unit. Could be an apartment, or house, whatever, it's available
  for short term rental. It can be listed on multiple channels such as Airbnb.
  See listings.models.Listing """
  airbnb_address_scrape = models.TextField(help_text=(
      'This is the address as scraped off Airbnb verbatim. Just... '
      'hang onto this field to make our lives easier for now.'))
  city = models.CharField(max_length=200, default='')
  time_zone = models.CharField(
      max_length=40, default='US/Eastern', choices=(
          (tz, tz) for tz in pytz.all_timezones))
  currency = models.CharField(
      max_length=3, default='USD', choices=sorted(
          ((c, c) for c in moneyed.CURRENCIES.keys())))
  accommodates = models.PositiveIntegerField(help_text=(
      'How many people can sleep here.'))
  bathrooms = models.PositiveIntegerField()
  bedrooms = models.PositiveIntegerField()
  property_type = models.CharField(max_length=50, help_text=(
      'Keep this vague until I know what the exhaustive enumeration '
      'of possible values is.'))
  room_type = models.CharField(max_length=50, help_text=(
      'Keep this vague until I know what the exhaustive enumeration '
      'of possible values is.'))
  owner = models.ForeignKey(Owner, null=True, on_delete=models.CASCADE)
  airvatar = models.ForeignKey(Airvatar, null=True, on_delete=models.CASCADE)

  class Meta:
    ordering = ['airbnb_address_scrape']

  def set_timezone(self, dt):
    """ Return the given datetime with the timezone set to the timezone of this
    rental. """
    if is_aware(dt):
      return dt
    return make_aware(dt, pytz.timezone(self.time_zone))

  def set_currency(self, m):
    """ Return the given money with the currency set to the currency of this
    rental. """
    if m.__class__ is Money:
      return Money(m.amount, self.currency)
    return Money(m, self.currency)

  def __str__(self):
    return self.airbnb_address_scrape

  def __repr__(self):
    return 'Rental({})'.format(self.airbnb_address_scrape)
