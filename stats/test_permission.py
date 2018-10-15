from rentals.tests import get_test_rental, get_test_owner
from stats.permission import Checker
from util.tests import TestCase


class PermissionTests(TestCase):
  def test_get_permission_problems(self):
    checker = Checker()
    rental = get_test_rental(True)
    not_owner = get_test_owner(True, username='blargh')
    self.assertIsNone(checker.get_permission_problems(rental.building.owner))
    self.assertIsNone(checker.get_permission_problems(
        rental.building.owner, rental_id=rental.pk))
    self.assertEqual(403, checker.get_permission_problems(
        not_owner, rental_id=rental.pk).status_code)
    self.assertIsNone(checker.get_permission_problems(
        rental.building.owner, owner_id=rental.building.owner.pk))
    self.assertEqual(403, checker.get_permission_problems(
        not_owner, owner_id=rental.building.owner.pk).status_code)
