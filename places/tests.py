from django.test import TestCase
from places.models import Host


class HostTests(TestCase):
  def test_save_and_load(self):
    Host.objects.create(name='Jane from L.A.')
    jane = Host.objects.get(name='Jane from L.A.')
    self.assertTrue(jane.id, 'Jane exists.')
