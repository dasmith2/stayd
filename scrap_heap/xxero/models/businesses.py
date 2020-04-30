""" A Business is what I'm calling the top level organization in Xero. Examples
are Stayd Inc and ExecResidence Housing LLC. You can see them in the top left
drop down on Xero. In Xero land, each Business gets its own Chart of Accounts,
its own bank accounts, its own transactions, all that stuff. It's only because
we have "consumer keys" for each Business that we are able to see all the data.
"""

from django.conf import settings
from django.db import models

from xxero.api import API


OWNER = 'OWNER'
OPERATOR = 'OPERATOR'


class BusinessManager(models.Manager):
  def get_all(self):
    self.init_businesses()
    return self.all()

  def init_businesses(self):
    # I used to have global state describing whether or not this was
    # initialized, but that caused havoc in tests because the global state
    # would say, yep, I'm initialized, but the django framework would clean out
    # the database after every test.
    if not self.exists():
      self._init_business(
          'STAYD Inc', settings.XERO_HI_HOWARD_OPERATIONS_CONSUMER_KEY)
      self._init_business(
          'ExecResidence Housing LLC',
          settings.XERO_EXEC_RESIDENCE_CONSUMER_KEY)

  def _init_business(self, name, consumer_key):
    business = self.filter(name=name).first()
    if not business:
      business = Business(name=name)
    if business.consumer_key != consumer_key:
      business.consumer_key = consumer_key
      business.save()

  def get_api_lookup(self):
    self.init_businesses()
    lookup = {}
    for business in self.all():
      lookup[business.consumer_key] = API(business.consumer_key)
    return lookup

  def get_operator(self):
    return self.get(
        consumer_key=settings.XERO_HI_HOWARD_OPERATIONS_CONSUMER_KEY)


class Business(models.Model):
  name = models.CharField(max_length=100)
  # There are additional comments on how to make a consumer key in
  # stayd/settings.py
  consumer_key = models.CharField(max_length=100, help_text=(
      'These are our credentials allowing us to log into the Xero API on '
      'behalf of this Business. To see a list of keys or make a new one, log '
      'in to https://developer.xero.com/myapps/'))

  objects = BusinessManager()

  def is_operator(self):
    return self.consumer_key == settings.XERO_HI_HOWARD_OPERATIONS_CONSUMER_KEY

  def is_owner(self):
    return not self.is_operator()

  def get_operator_or_owner(self):
    if self.is_operator():
      return OPERATOR
    return OWNER

  def get_api(self, api_lookup=None):
    api_lookup = api_lookup or Business.objects.get_api_lookup()
    return api_lookup[self.consumer_key]

  def __repr__(self):
    return '<Business {}: {}>'.format(self.pk, self.name)
