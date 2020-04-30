from decimal import Decimal

from stats.models.stats import Stats
from util.tests import TestCase


class StatsTests(TestCase):
  def test_nps(self):
    stats = Stats()
    stats.total_nps_scores = 4
    stats.promoters = 2
    stats.detractors = 1
    self.assertEqual(25, stats.nps())

    stats.total_nps_scores = 2
    stats.promoters = 1
    stats.detractors = 1
    self.assertEqual(0, stats.nps())

  def test_describe_expenses(self):
    stats = Stats()
    stats.rent = Decimal('3000.00')
    expected = [
        ('Rent', Decimal('3000.0')),
        ('Total expenses', Decimal('3000.0')),
        ('Pro rated expenses', Decimal('1500.0'))]
    self.assertEqual(
        expected, stats.describe_expenses(pro_rated_fraction=.5))
    expected = [
        ('Rent', Decimal('3000.0')),
        ('Total expenses', Decimal('3000.0'))]
    self.assertEqual(expected, stats.describe_expenses())

  def test_describe_revenue(self):
    stats = Stats()
    stats.rooms_revenue = Decimal('10.0')
    expected = [
        ('Rooms revenue', Decimal('10.0')),
        ('Total revenue', Decimal('10.0')),
        ('Pro rated revenue', Decimal('5.0'))]
    self.assertEqual(
        expected, stats.describe_revenue(pro_rated_fraction=.5))
    expected = [
        ('Rooms revenue', Decimal('10.0')),
        ('Total revenue', Decimal('10.0'))]
    self.assertEqual(expected, stats.describe_revenue())
