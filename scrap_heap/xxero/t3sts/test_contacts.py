import copy
from unittest.mock import Mock
from uuid import uuid4 as random_uuid

from util.tests import TestCase
from xxero.api import API
from xxero.api_examples import CONTACT
from xxero.models.contacts import Contact
from xxero.tests.test_businesses import get_test_business


def get_test_contact(**kwargs):
  business = kwargs.get('business', None)
  if not business:
    business = get_test_business(**kwargs)
  return Contact.objects.create(
      contact_id=kwargs.get('contact_id', random_uuid()),
      name=kwargs.get('name', 'Amazon'),
      business=business)


class ContactTests(TestCase):
  def test_get_by_name(self):
    business1 = get_test_business()
    business2 = get_test_business()
    existing_contact_1 = copy.deepcopy(CONTACT)
    existing_contact_1['ContactID'] = '11111111-1111-1111-1111-111111111111'
    existing_contact_1['Name'] = 'Double catfish'
    existing_contact_2 = copy.deepcopy(CONTACT)
    existing_contact_2['ContactID'] = '22222222-2222-2222-2222-222222222222'
    existing_contact_2['Name'] = 'Double catfish'

    api = Mock(spec=API)
    api.contact.side_effect = [existing_contact_1, existing_contact_2]

    Contact.objects.get_by_name('Double catfish', business1, api=api)
    Contact.objects.get_by_name('Double catfish', business2, api=api)

    Contact.objects.get(
        contact_id='11111111-1111-1111-1111-111111111111',
        name='Double catfish', business=business1)
    Contact.objects.get(
        contact_id='22222222-2222-2222-2222-222222222222',
        name='Double catfish', business=business2)
