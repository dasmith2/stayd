import moneyed
import pytz
from djmoney.money import Money
from django.db import models
from django.utils.timezone import make_aware, is_aware

from pays.models import Payable


class Owner(Payable):
  name = models.CharField(max_length=100, default='')

  def __str__(self):
    return self.name


class PayoutRule(models.Model):
  percent = models.DecimalField(decimal_places=4, max_digits=5, help_text=(
      'What percent of the rental income does the owner receive?'))
  days_after_payment = models.PositiveIntegerField(help_text=(
      'How many days after we got paid do they get paid?'))
  goes_into_effect = models.DateTimeField()
  owner = models.ForeignKey(Owner, on_delete=models.CASCADE)

  def __str__(self):
    return 'Pay {} {}% {} days after we get paid starting {}'.format(
        self.owner, int(self.percent * 100), self.days_after_payment,
        self.goes_into_effect)


class Rental(models.Model):
  airbnb_address_scrape = models.TextField(help_text=(
      'This is the address as scraped off Airbnb verbatim. Just... '
      'hang onto this field to make our lives easier for now.'))
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
