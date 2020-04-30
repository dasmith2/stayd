""" This stuff should all be good to run on stage as part of continuous
integration. So don't include Selenium in here anywhere, which runs only on
local development environments. """
from datetime import date, time as datetime_time
from decimal import Decimal
import re
import time as time_time

from django.conf import settings
from django.contrib.auth.models import User, Group
from django.shortcuts import reverse
from django.test import Client, TestCase as DjangoTestCase

from util.random_string import random_string
from util.timezone import (
    past_x_months, PastMonth, str_to_tz_dt, years_old, time_str_to_time)
from util.views import homepage_by_host


class FakeResponse(object):
  """ This class should go away. APIs should raise ServerErrors and NotOkErrors
  when they encounter problems, and return data when they don't. I don't want
  developers to have to remember to check status codes or the contents of every
  api call. That should happen automatically. Then when APIs have issues,
  exceptions get raised, we get emailed, and we figure out how to handle that
  particular case. """
  def __init__(self, ok, json, status_code=200):
    self.ok = ok
    self._json = json
    self.status_code = status_code

  def json(self):
    if self._json is None:
      raise Exception()
    return self._json


class TestCase(DjangoTestCase):
  mobile_client = Client(HTTP_USER_AGENT=settings.EXAMPLE_MOBILE_USER_AGENT)

  def setUp(self):
    self._started_at = time_time.time()

  def tearDown(self):
    if not hasattr(self, '_started_at'):
      raise Exception(
          'You probably need to put a call to super().setUp() in your setUp.')
    elapsed = time_time.time() - self._started_at
    if elapsed > 1.0:
      print('\n{} ({}s)'.format(self.id(), round(elapsed, 2)))

  def assert_no_invalid_variables(self, content):
    found = re.compile(r'(Invalid variable: [\w\.]+)').search(content)
    if found:
      self.fail(found.groups()[0])

  def get(self, url, assert_status=200):
    resp = self.client.get(url)
    self.assertEqual(resp.status_code, assert_status)
    content = resp.content.decode('utf-8')
    self.assert_no_invalid_variables(content)
    return content

  def write_get_to_file(self, url):
    print('Writing {} to ../test.html'.format(url))
    write_to = open('../test.html', 'w')
    write_to.write(self.get(url))
    write_to.close()

  def assert_get_contains(
      self, url, check_for, assert_status=200, write_to=None):
    content = self.get(url, assert_status)
    if write_to:
      write_to_file = open(write_to, 'w')
      write_to_file.write(content)
      write_to_file.close()
    self.assertTrue(content.find(check_for) >= 0)

  def assert_get_not_contains(self, url, check_for, assert_status=200):
    self.assertEqual(-1, self.get(url, assert_status).find(check_for))

  def assert_dec_equal(self, decimal_first, decimal_second):
    diff = decimal_first - decimal_second
    if diff < Decimal('-.001') or Decimal('.001') < diff:
      self.assertTrue(False, '{} != {}'.format(decimal_first, decimal_second))

  def login(self, group=None, is_staff=True, is_superuser=False, user=None):
    user = user or get_test_user(is_staff=is_staff, is_superuser=is_superuser)
    if group:
      group_obj = Group.objects.get_or_create(name=group)[0]
      if group_obj not in user.groups.all():
        user.groups.add(group_obj)
    self.client.force_login(user)


def get_test_group(**kwargs):
  return Group.objects.create(name=kwargs.get('name', 'whatever'))


def get_test_user(**kwargs):
  """ This does get used by functions like high_risk_submission which are handy
  in web tests and in unit tests. """
  username = kwargs.get('username', None)
  if settings.RUNSERVER and not username:
    raise Exception(
        'Please dont create random test users in a persistent database')
  if username:
    existing = User.objects.filter(username=username).first()
    if existing:
      return existing
  user = User.objects.create(
      password=kwargs.get('password', 'asdf'),
      is_superuser=kwargs.get('is_superuser', False),
      username=kwargs.get('username', 'billyblue' + random_string(5)),
      first_name=kwargs.get('first_name', 'billy'),
      last_name=kwargs.get('last_name', 'blue'),
      email=kwargs.get('email', 'billyblue@email.com'),
      is_staff=kwargs.get('is_staff', False),
      is_active=kwargs.get('is_active', True))
  groups = kwargs.get('groups', [])
  for group in groups:
    existing = Group.objects.filter(name=group).first()
    if not existing:
      existing = get_test_group(name=group)
    user.groups.add(existing)
  return user


class HomepageRedirectTests(TestCase):
  def test_homepage_redirect(self):
    self.assertEqual('/dashboard/', homepage_by_host('owners'))
    self.assertEqual('/verify_id/', homepage_by_host('guests'))
    self.assertEqual(reverse('submissions'), homepage_by_host('admin'))
    self.assertEqual('/clean_co_cleanings/', homepage_by_host('clean'))
    self.assertEqual('/admin', homepage_by_host('whatever else'))


class Past12MonthsTests(TestCase):
  def test_past_x_months(self):
    expected = [
        PastMonth(year=2019, month=8, months_ago=0),
        PastMonth(year=2019, month=7, months_ago=1),
        PastMonth(year=2019, month=6, months_ago=2),
        PastMonth(year=2019, month=5, months_ago=3),
        PastMonth(year=2019, month=4, months_ago=4),
        PastMonth(year=2019, month=3, months_ago=5),
        PastMonth(year=2019, month=2, months_ago=6),
        PastMonth(year=2019, month=1, months_ago=7),
        PastMonth(year=2018, month=12, months_ago=8),
        PastMonth(year=2018, month=11, months_ago=9),
        PastMonth(year=2018, month=10, months_ago=10),
        PastMonth(year=2018, month=9, months_ago=11)]
    got = list(past_x_months(12, nnow=str_to_tz_dt('2019-08-28 14:46')))
    self.assertEqual(expected, got)


class YearsOldTests(TestCase):
  def test_years_old(self):
    self.assertEqual(None, years_old(None))
    self.assertEqual(0, years_old(
        date(2018, 1, 1), nnow=str_to_tz_dt('2018-01-01')))
    self.assertEqual(0, years_old(
        date(2018, 1, 1), nnow=str_to_tz_dt('2018-01-02')))
    self.assertEqual(0, years_old(
        date(2018, 12, 2), nnow=str_to_tz_dt('2019-12-01')))
    self.assertEqual(1, years_old(
        date(2018, 12, 2), nnow=str_to_tz_dt('2019-12-02')))
    self.assertEqual(1, years_old(
        date(2018, 12, 2), nnow=str_to_tz_dt('2020-12-01')))


class TimeStrToTimeTests(TestCase):
  def test_time_str_to_time(self):
    self.assertEqual(datetime_time(0, 0), time_str_to_time('00:00'))
    self.assertEqual(datetime_time(0, 0), time_str_to_time('12:00 AM'))
    self.assertEqual(datetime_time(11, 59), time_str_to_time('11:59'))
    self.assertEqual(datetime_time(11, 59), time_str_to_time('11:59 AM'))
    self.assertEqual(datetime_time(12, 0), time_str_to_time('12:00'))
    self.assertEqual(datetime_time(12, 0), time_str_to_time('12:00 PM'))
    self.assertEqual(datetime_time(23, 59), time_str_to_time('11:59 PM'))
    self.assertEqual(None, time_str_to_time(None))
