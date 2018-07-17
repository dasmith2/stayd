from django.conf import settings
from django.contrib.auth.models import User, Group
from django.test import Client, TestCase as DjangoTestCase


def is_test():
  return settings.TEST


class TestCase(DjangoTestCase):
  mobile_client = Client(HTTP_USER_AGENT=settings.EXAMPLE_MOBILE_USER_AGENT)

  def assertGetContains(self, url, check_for):
    resp = self.client.get(url)
    self.assertEqual(resp.status_code, 200)
    self.assertTrue(resp.content.decode('utf-8').find(check_for) >= 0)


def get_test_group(create, **kwargs):
  group = Group(name=kwargs.get('name', 'whatever'))
  if create:
    group.save()
  return group


def get_test_user(create, **kwargs):
  user = User(
      password=kwargs.get('password', 'asdf'),
      is_superuser=kwargs.get('is_superuser', False),
      username=kwargs.get('username', 'billyblue'),
      first_name=kwargs.get('first_name', 'billy'),
      last_name=kwargs.get('last_name', 'blue'),
      email=kwargs.get('email', 'billyblue@email.com'),
      is_staff=kwargs.get('is_staff', False),
      is_active=kwargs.get('is_active', True))
  if create:
    user.save()
  groups = kwargs.get('groups', [])
  if groups and not create:
    raise Exception('You can only add a created user to groups.')
  for group in groups:
    existing = Group.objects.filter(name=group).first()
    if not existing:
      existing = get_test_group(True, name=group)
    user.groups.add(existing)
  return user
