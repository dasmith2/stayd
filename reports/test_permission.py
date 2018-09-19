from django.contrib.auth.models import User

from rentals.tests import get_test_rental, get_test_owner
from reports.permission import Checker
from util.tests import TestCase


class PermissionTests(TestCase):
  def test_can_view_owner(self):
    checker = Checker()
    owner = get_test_owner(True, username='whatever')
    self.assertTrue(checker.can_view_owner(owner, 0))
    self.assertTrue(checker.can_view_owner(owner, owner.pk))
    staff = User.objects.create(username='staff', is_staff=True)
    self.assertTrue(checker.can_view_owner(staff, owner.pk))
    other_owner = get_test_owner(True, username='other_owner')
    self.assertFalse(checker.can_view_owner(other_owner, owner.pk))

  def test_can_view_rental(self):
    checker = Checker()
    rental = get_test_rental(True)
    self.assertTrue(checker.can_view_rental(rental.owner, None))
    self.assertTrue(checker.can_view_rental(rental.owner, rental))
    staff = User.objects.create(username='staff', is_staff=True)
    self.assertTrue(checker.can_view_rental(staff, rental))
    other_owner = get_test_owner(True, username='other_owner')
    self.assertFalse(checker.can_view_rental(other_owner, rental))
