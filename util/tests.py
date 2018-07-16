import sys

from django.conf import settings
from django.test import Client, TestCase as DjangoTestCase


def is_test():
  return 'test' in sys.argv


class TestCase(DjangoTestCase):
  mobile_client = Client(HTTP_USER_AGENT=settings.EXAMPLE_MOBILE_USER_AGENT)
