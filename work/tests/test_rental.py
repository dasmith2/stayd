from djmoney.money import Money

from work.api import API
from work.api_examples import SET_SOURCE_PROPERTY_ID_RESPONSE
from work.models.rental import ProperlyRental
from rentals.tests import get_test_rental
from unittest.mock import Mock, call
from util.network import CantUseTheNet
from util.random_string import random_string
from util.tests import TestCase


def get_test_properly_rental(**kwargs):
  rental = kwargs.get('rental', None)
  if not rental:
    rental = get_test_rental(**kwargs)
  properly_property_id = kwargs.get('properly_property_id', random_string(10))
  source_property_id = kwargs.get('source_property_id', properly_property_id)
  clean_co = kwargs.get('clean_co', None)
  cleaning_flat_rate = kwargs.get('cleaning_flat_rate', None)
  if clean_co and 'cleaning_flat_rate' not in kwargs:
    cleaning_flat_rate = Money('100', 'USD')
  return ProperlyRental.objects.create(
      rental=kwargs.get('rental', rental),
      properly_property_id=properly_property_id,
      source_property_id=source_property_id,
      clean_co=clean_co,
      cleaning_flat_rate=cleaning_flat_rate)


class ProperlyRentalTests(TestCase):
  def test_set_and_clear_source_property_id(self):
    # cleaning.py has a post save signal that kicks off a background task to
    # set the source_property_id when a rental checklist gets saved with a
    # properly_property_id but no source_property_id. I can't work out how to
    # get my mock in there.
    try:
      get_test_properly_rental(
          properly_property_id='goatsandboats', source_property_id=None)
    except CantUseTheNet:
      pass
    pr = ProperlyRental.objects.get(properly_property_id='goatsandboats')
    self.assertIsNone(pr.source_property_id)
    api = Mock(spec=API)
    api.property_update.return_value = SET_SOURCE_PROPERTY_ID_RESPONSE
    self.assertEqual('goatsandboats', pr.get_source_property_id(api=api))
    pr.refresh_from_db()
    self.assertEqual(pr.source_property_id, 'goatsandboats')
    expected = {
        'propertyId': 'goatsandboats',
        'changes': {'sourceId': 'goatsandboats'}}
    self.assertEqual([call(expected)], api.property_update.call_args_list)

    # Now clear it out.
    pr.properly_property_id = ''
    pr.save()
    self.assertEqual('', pr.source_property_id)
