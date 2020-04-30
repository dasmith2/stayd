from netsuite.models.category_by_channel import CategoryByChannel
from util.channels import AIRBNB


def get_test_category_by_channel(**kwargs):
  channel = kwargs.get('channel', AIRBNB)
  existing = CategoryByChannel.objects.filter(channel=channel).first()
  if existing:
    return existing
  return CategoryByChannel.objects.create(
      channel=kwargs.get('channel', None),
      sales_category_name=kwargs.get('sales_category_name', None),
      sales_category_id=kwargs.get('sales_category_id', None),
      fee_category_name=kwargs.get('fee_category_name', None),
      fee_category_id=kwargs.get('fee_category_id', None))
