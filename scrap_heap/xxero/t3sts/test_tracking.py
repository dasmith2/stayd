from util.tests import TestCase
from uuid import UUID, uuid4 as random_uuid
from xxero.api_examples import TRACKING_CATEGORY
from xxero.models.tracking import TrackingCategory, TrackingOption
from xxero.tests.test_businesses import get_test_business


def get_test_tracking_category(**kwargs):
  business = kwargs.get('business', None)
  if not business:
    business = get_test_business(**kwargs)
  return TrackingCategory.objects.create(
      tracking_category_id=kwargs.get(
          'tracking_category_id', random_uuid()),
      name=kwargs.get('name', 'Mikes place'),
      business=business)


def get_test_tracking_option(**kwargs):
  tracking_category = kwargs.get('tracking_category', None)
  if not tracking_category:
    tracking_category = get_test_tracking_category(**kwargs)
  return TrackingOption.objects.create(
      tracking_category=tracking_category,
      tracking_option_id=kwargs.get(
          'tracking_option_id', random_uuid()),
      name=kwargs.get('name', 'tracking option name here'),
      building=kwargs.get('building', None))


class TrackingCategoryTests(TestCase):
  def test_sync_options(self):
    tracking_category = get_test_tracking_category()
    tracking_category.sync_options(TRACKING_CATEGORY)
    self.assertEqual(1, tracking_category.trackingoption_set.count())
    option = tracking_category.trackingoption_set.first()
    self.assertEqual(
        UUID('f9b54796-b921-4fd4-97b3-23f8cb5a5bf0'),
        option.tracking_option_id)
    self.assertEqual('243 Montgomery Street, Jersey City', option.name)
