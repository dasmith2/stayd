from datetime import date, timedelta

from django.shortcuts import reverse
from djmoney.money import Money

from dashboard.models import get_buildings, get_from_today_to, get_month_totals
from rentals.tests import (
    get_test_owner, get_test_building, get_test_rental)
from reservations.models import ReservationLineItem, KNOWN_LINE_ITEM_NAMES
from reservations.tests import get_test_reservation
from stats.models.stale import Stale
from util.tests import TestCase


def get_dashboard_reservation(building, date, income, expenses):
  res = get_test_reservation(
      True, building=building, check_in=date,
      check_out=date + timedelta(days=1))
  ReservationLineItem.objects.create(
      name=KNOWN_LINE_ITEM_NAMES.RENT,
      value=Money(income, 'USD'),
      reservation=res)
  ReservationLineItem.objects.create(
      name=KNOWN_LINE_ITEM_NAMES.AIRBNB_SERVICE_FEE,
      value=Money(-expenses, 'USD'),
      reservation=res)


class DashboardTests(TestCase):
  def test_get_month_totals(self):
    owner = get_test_owner(True, username='owner_here')
    yes_building = get_test_building(True, owner=owner)
    no_building = get_test_building(True, owner=owner)

    # Too early.
    get_dashboard_reservation(yes_building, date(2017, 10, 15), 100, 0)
    # Should count towards the previous 3 months calculation
    get_dashboard_reservation(yes_building, date(2017, 11, 2), 140, 0)
    get_dashboard_reservation(no_building, date(2017, 11, 2), 20, 0)
    # Regarding the January amounts.
    get_dashboard_reservation(yes_building, date(2018, 1, 12), 300, 10)
    get_dashboard_reservation(no_building, date(2018, 1, 12), 30, 20)
    # In this month before today
    get_dashboard_reservation(yes_building, date(2018, 2, 12), 400, 70)
    get_dashboard_reservation(no_building, date(2018, 2, 12), 40, 13)
    # In this month after today
    get_dashboard_reservation(yes_building, date(2018, 2, 16), 500, 15)
    get_dashboard_reservation(no_building, date(2018, 2, 16), 50, 0)
    # Next month
    get_dashboard_reservation(yes_building, date(2018, 3, 1), 600, 20)
    get_dashboard_reservation(no_building, date(2018, 3, 1), 60, 30)

    Stale.objects.redo_all_stats()

    from_date = date(2018, 1, 1)
    today = date(2018, 2, 15)
    to_date = date(2018, 5, 1)

    historic_month_income = [10, 20, 10, 20, 10, 20, 10, 20, 10, 20, 10, 20]
    totals = get_month_totals(
        from_date, today, to_date, owner.pk, yes_building.pk,
        historic_month_income)

    self.assertEqual(4, len(totals))

    self.assertEqual(date(2018, 1, 1), totals[0].from_date)
    self.assertEqual(None, totals[0].projected_income)
    self.assertEqual(300, totals[0].past_income)
    self.assertEqual(10, totals[0].past_expenses)
    self.assertEqual(290, totals[0].past_profit)
    self.assertEqual(None, totals[0].booked_income)
    self.assertEqual(None, totals[0].booked_expenses)
    self.assertEqual(None, totals[0].booked_profit)

    # The previous 3 months, November and January, had $440 total profit. The
    # historic_month_income has 10 + 20 + 10 for Nov - Jan = $40 profit. So the
    # expected profit is 11 times whatever we've got in that months spot in
    # historic_month_income.

    self.assertEqual(date(2018, 2, 1), totals[1].from_date)
    self.assertEqual(220, totals[1].projected_income)
    self.assertEqual(400, totals[1].past_income)
    self.assertEqual(500, totals[1].booked_income)
    # On the overlap month we add the past and booked profit and expenses
    # together so that the lines line up.
    self.assertEqual(85, totals[1].past_expenses)
    self.assertEqual(85, totals[1].booked_expenses)
    self.assertEqual(815, totals[1].past_profit)
    self.assertEqual(815, totals[1].booked_profit)

    self.assertEqual(date(2018, 3, 1), totals[2].from_date)
    self.assertEqual(110, totals[2].projected_income)
    self.assertEqual(None, totals[2].past_income)
    self.assertEqual(600, totals[2].booked_income)
    self.assertEqual(20, totals[2].booked_expenses)
    self.assertEqual(580, totals[2].booked_profit)
    self.assertEqual(None, totals[2].past_expenses)
    self.assertEqual(None, totals[2].past_profit)

    self.assertEqual(date(2018, 4, 1), totals[3].from_date)
    self.assertEqual(220, totals[3].projected_income)
    self.assertEqual(None, totals[3].past_income)
    self.assertEqual(0, totals[3].booked_income)

    # And hey, as long as we got this all set up, let's run the view.
    self.client.force_login(owner)
    self.get(reverse('dashboard') + '?date=2018-02-15')

  def test_get_from_today_to(self):
    from_date, today, to_date = get_from_today_to(date(2018, 11, 12))
    self.assertEqual(date(2018, 1, 1), from_date)
    self.assertEqual(date(2018, 11, 12), today)
    self.assertEqual(date(2019, 2, 1), to_date)

  def test_get_buildings(self):
    owner = get_test_owner(True, username='yep_this_owner')

    yes_building = get_test_building(True, owner=owner)
    get_test_rental(True, building=yes_building)
    get_test_rental(True, building=yes_building)

    building_inactive = get_test_building(True, owner=owner, is_active=False)
    get_test_rental(True, building=building_inactive)
    get_test_rental(True, building=building_inactive)

    building_other_owner = get_test_building(
        True, owner=get_test_owner(True, username='nope_other_owner'))
    get_test_rental(True, building=building_other_owner)
    get_test_rental(True, building=building_other_owner)

    get_test_building(True, owner=owner)  # No rentals.

    # If you've only got one building, don't include a total building.
    buildings = get_buildings(owner.pk)
    self.assertEqual(1, len(buildings))
    self.assertEqual(buildings[0], yes_building)

    # If you have 2 or more buildings, also include a total building.
    yes_building_2 = get_test_building(True, owner=owner)
    get_test_rental(True, building=yes_building_2)

    buildings = get_buildings(owner.pk)
    self.assertEqual(3, len(buildings))
    total_building = buildings[0]
    self.assertEqual(3, total_building.rentals)
    self.assertEqual(None, total_building.pk)
