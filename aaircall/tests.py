from datetime import timedelta
from unittest.mock import Mock, call

from aaircall.api import API
from aaircall.models import push_front_contacts_to_aaircall
from front.api import FrontAPI
from front.api_examples import CONTACTS
from util.tests import TestCase
from util.timezone import ts_to_utc_dt


class AaircallTests(TestCase):
  def test_raw_event_post_save(self):
    api = Mock(spec=API)
    api.get_contact.return_value = {'id': 'blargh', 'first_name': 'different'}
    front_api = Mock(spec=FrontAPI)
    front_api.get_contacts.return_value = CONTACTS['_results']

    # This timestamp is right between the updated_at of the two contact datas
    # in CONTACTS
    modified_since = ts_to_utc_dt(1553609962)
    nnow = modified_since + timedelta(days=3)

    push_front_contacts_to_aaircall(
        api=api, front_api=front_api,
        modified_since=nnow - timedelta(days=3))

    self.assertEqual(
        [call(next_url=None)],
        front_api.get_contacts.call_args_list)
    self.assertEqual([call('+491711438542')], api.get_contact.call_args_list)
    expected = {
        'id': 'blargh',
        'first_name': 'Anja Woinowsky 12 Saddlewood Ct',
        'phone_numbers': [{'label': 'work', 'value': '+491711438542'}],
        'information': (
            'checkin: 2019-06-01 16:00\ncheckout: 2019-06-04 11:00\n'
            'city: Jersey City\n'
            'https://app.guesty.com/reservations/'
            '5c73e9edc55264004c449691/guests')}
    self.assertEqual([call(expected)], api.save_contact.call_args_list)
