""" These are pretty much the building, and the Bento card used to make the
transaction. """
from django.db import models

from rentals.models import Building
from xxero.api import API
from xxero.models.businesses import Business


class TrackingCategoryManager(models.Manager):
  def get_by_name(self, name, api=None):
    api = api or API()
    existing = self.filter(name=name).first()
    if existing:
      return existing
    xero_existing = api.get_tracking_category_by_name(name)
    if xero_existing:
      return self.sync(xero_existing)
    return self.sync(api.create_tracking_category(name))

  def sync(self, tracking_category_dict):
    tracking_category_id = tracking_category_dict['TrackingCategoryID']
    tracking_category = self.filter(
        tracking_category_id=tracking_category_id).first()
    if not tracking_category:
      tracking_category = TrackingCategory(
          tracking_category_id=tracking_category_id)
    tracking_category.name = tracking_category_dict['Name']
    tracking_category.save()
    tracking_category.sync_options(tracking_category_dict)
    return tracking_category


class TrackingCategory(models.Model):
  """ Transactions have line items. Line items have up to 2 tracking
  categories. https://developer.xero.com/documentation/api/tracking-categories
  """
  tracking_category_id = models.UUIDField(db_index=True, unique=True)
  name = models.CharField(max_length=300)
  business = models.ForeignKey(
      Business, on_delete=models.CASCADE, blank=True, null=True)

  objects = TrackingCategoryManager()

  def get_xero(self, api=None):
    api = api or API()
    return api.trackingcategories.get(self.tracking_category_id)

  def get_option(self, name, api=None):
    api = api or API()
    existing = self.trackingoption_set.filter(name=name).first()
    if not existing:
      self.sync_options(api.tracking_category(self.tracking_category_id))
      existing = self.trackingoption_set.filter(name=name).first()
    if existing:
      return existing
    tracking_option_id = api.create_tracking_option(
        self.tracking_category_id, name)
    return TrackingOption.objects.create(
        tracking_category=self,
        tracking_option_id=tracking_option_id,
        name=name)

  def sync_option(self, option_dict):
    tracking_option_id = option_dict['TrackingOptionID']
    option = TrackingOption.objects.filter(
        tracking_category=self, tracking_option_id=tracking_option_id).first()
    if not option:
      option = TrackingOption(
          tracking_category=self,
          tracking_option_id=tracking_option_id)
    option.name = option_dict['Name']
    option.save()
    return option

  def sync_options(self, tracking_category_dict):
    for option_dict in tracking_category_dict['Options']:
      self.sync_option(option_dict)

  def __repr__(self):
    return '<TrackingCategory {}: {} {}>'.format(
        self.pk, self.tracking_category_id, self.name)

  def __str__(self):
    return self.__repr__()


class TrackingOptionManager(models.Manager):
  def sync_option(self, business, tracking_data, bank_transaction_id):
    """ tracking_data is like {'Name': 'Card',
      'Option': '243 Montgomery BLDG',
      'TrackingCategoryID': 'cf510f12-341c-4187-afc4-47aab451fc71',
      'TrackingOptionID': '158b715a-3463-432e-adca-abcf061ef43e'} """
    category_id = tracking_data['TrackingCategoryID']
    category_name = tracking_data['Name']
    tracking_category = TrackingCategory.objects.filter(
        business=business, tracking_category_id=category_id,
        name=category_name).first()
    if not tracking_category:
      tracking_category = self._possibly_create_category(
          business, category_id, category_name, bank_transaction_id)
    option_id = tracking_data['TrackingOptionID']
    option_name = tracking_data['Option']
    option = self._get_or_create_option(
        tracking_category, option_id, option_name, bank_transaction_id)
    return option

  def _possibly_create_category(
      self, business, category_id, category_name, bank_transaction_id):
    category_by_id = TrackingCategory.objects.filter(
        tracking_category_id=category_id, business=business).first()
    category_by_name = TrackingCategory.objects.filter(
        name=category_name, business=business).first()
    conflict = category_by_id or category_by_name
    if conflict:
      message = (
          'Tracking category {} {} already exists but transaction {} '
          'describes a conflicting category {} {}').format(
              conflict.name, conflict.tracking_category_id,
              bank_transaction_id, category_id, category_name)
      raise Exception(message)
    return TrackingCategory.objects.create(
        business=business, tracking_category_id=category_id,
        name=category_name)

  def _get_or_create_option(
      self, tracking_category, option_id, option_name, bank_transaction_id):
    option = tracking_category.trackingoption_set.filter(
        tracking_option_id=option_id).first()
    if option:
      if option.name != option_name:
        option.name = option_name
        option.save()
      return option
    return TrackingOption.objects.create(
        tracking_category=tracking_category, tracking_option_id=option_id,
        name=option_name)


class TrackingOption(models.Model):
  tracking_category = models.ForeignKey(
      TrackingCategory, on_delete=models.CASCADE)
  tracking_option_id = models.UUIDField(unique=True)
  name = models.CharField(max_length=300)
  building = models.ForeignKey(
      Building, on_delete=models.CASCADE, null=True, blank=True, help_text=(
          'The end goal of all this is tracking expenses back to a building.'))

  objects = TrackingOptionManager()

  def __repr__(self):
    return '<TrackingOption {}: {} {}>'.format(
        self.pk, self.name, self.tracking_option_id)

  class Meta:
    unique_together = (('tracking_category', 'name'),)
