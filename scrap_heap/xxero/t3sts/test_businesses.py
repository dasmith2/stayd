from django.conf import settings

from xxero.models.businesses import Business
from util.tests import TestCase


def get_test_business(**kwargs):
  return Business.objects.create(
      name=kwargs.get('name', 'Dave INC'),
      consumer_key=kwargs.get('consumer_key', 'sldkfnsldkfjsndndndjdjdjdjfff'))


class BusinessTests(TestCase):
  def test_init_businesses(self):
    for i in range(3):
      Business.objects.init_businesses()

    self.assertEqual(2, Business.objects.count())
    stayd = Business.objects.get(
        name='STAYD Inc',
        consumer_key=settings.XERO_HI_HOWARD_OPERATIONS_CONSUMER_KEY)
    self.assertTrue(stayd.is_operator())
    execres = Business.objects.get(
        name='ExecResidence Housing LLC',
        consumer_key=settings.XERO_EXEC_RESIDENCE_CONSUMER_KEY)
    self.assertFalse(execres.is_operator())

  def test_get_api_lookup(self):
    lookup = Business.objects.get_api_lookup()
    self.assertEqual(2, len(lookup.keys()))
    exec_res_key = settings.XERO_EXEC_RESIDENCE_CONSUMER_KEY
    self.assertEqual(exec_res_key, lookup[exec_res_key].consumer_key)
    hi_howard_key = settings.XERO_HI_HOWARD_OPERATIONS_CONSUMER_KEY
    self.assertEqual(hi_howard_key, lookup[hi_howard_key].consumer_key)
