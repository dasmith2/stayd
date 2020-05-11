from django.conf import settings
from django.contrib.auth.models import Group, User

from util.permission import VIRTUAL_HOST_GROUP


SAME_PASSWORD = '97d2mk.Y'
SUPERUSER_USERNAME = 'superuser'
VIRTUAL_HOST_USERNAME = 'vh_veronica'


def get_superuser():
  user = get_web_test_user(SUPERUSER_USERNAME)
  user.email = 'super@user.com'
  user.is_superuser = True
  user.is_staff = True
  user.save()
  return user


def get_virtual_host():
  return get_web_test_user(VIRTUAL_HOST_USERNAME, groups=[VIRTUAL_HOST_GROUP])


def get_web_test_user(
    username, password=SAME_PASSWORD, groups=[]):
  """ OK, so you know how, in a web test, you have a laptop that opens a
  browser and then starts executing requests against a server. Well, this
  function only makes sense on the server. So I would expect this call to be
  in, like, my_app/views/web_test_views.py or whatever. I would NOT expect this
  call to be in my_app/management/commands/my_web_test.py because THAT code
  runs on the laptop. Now, typically, the server IS your laptop. So if you put
  a call to get_test_user in my_web_test.py, it'll work at first. But it'll
  fail when you do, like,
  ./manage.py my_web_test --server=https://stage.hihoward.com """
  if settings.PROD:
    raise Exception('Dont create test data on prod')
  user = User.objects.filter(username=username).first()
  if not user:
    user = User.objects.create(username=username)
  user.set_password(password)
  user.save()
  for group in groups:
    user.groups.add(Group.objects.get_or_create(name=group)[0])
  return user
