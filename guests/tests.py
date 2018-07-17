from datetime import date

from util.tests import TestCase
from guests.models import Guest


def get_test_guest(create, **kwargs):
  guest = Guest(
      first_name=kwargs.get('first_name', 'Ron'),
      full_name=kwargs.get('full_name', 'Ron Burgundy'),
      joined_airbnb_when=kwargs.get(
          'joined_airbnb_when', date(2017, 1, 1)),
      airbnb_says_theyre_from=kwargs.get(
          'airbnb_says_theyre_from', 'Boston, MA'),
      phone=kwargs.get('phone', '(555) 555-5555'),
      email=kwargs.get('email', ''))
  if create:
    guest.save()
  return guest


class GuestTests(TestCase):
  def test_get_if_exists__does_exist(self):
    match_me = {
        'full_name': 'Bob Boop',
        'joined_airbnb_when': date(2017, 2, 3),
        'airbnb_says_theyre_from': 'Queens, NY',
        'phone': '(666) 666-6666'}
    g_not_name = get_test_guest(  # noqa: F841
        True,
        full_name='Sam Sloop',
        joined_airbnb_when=date(2017, 2, 3),
        airbnb_says_theyre_from='Queens, NY',
        phone='(666) 666-6666')
    g_name_1_match = get_test_guest(  # noqa: F841
        True,
        full_name='Bob Boop',
        joined_airbnb_when=date(2017, 2, 3))
    g_name_2_matches = get_test_guest(
        True,
        full_name='Bob Boop',
        airbnb_says_theyre_from='Queens, NY',
        phone='(666) 666-6666')
    self.assertEqual(g_name_2_matches, Guest.objects.get_if_exists(**match_me))

  def test_get_if_exists__does_not_exist(self):
    match_me = {
        'full_name': 'Dave Doop',
        'joined_airbnb_when': date(2016, 2, 3),
        'airbnb_says_theyre_from': 'Brooklyn, NY',
        'phone': '(777) 777-7777'}
    g_everything_but_name = get_test_guest(  # noqa: F841
        True,
        full_name='Jane Joop',
        joined_airbnb_when=date(2016, 2, 3),
        airbnb_says_theyre_from='Brooklyn, NY',
        phone='(777) 777-7777')
    g_only_name = get_test_guest(  # noqa: F841
        True,
        full_name='Dave Doop')
    self.assertIsNone(Guest.objects.get_if_exists(**match_me))
