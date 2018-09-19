from rentals.tests import get_test_rental
from reports.permission import Checker
from util.tests import TestCase


class PermissionTests(TestCase):
  def test_can_view_owner(self):
    
    self.assertTrue(Checker().can_view_owner(
    viewing_user, owner_id
