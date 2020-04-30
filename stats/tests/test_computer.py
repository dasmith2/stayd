from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from djmoney.money import Money

from expenses.models import DAYS_OF_THE_MONTH
from expenses.tests import get_test_expense
from nps.tests.test_rating import get_test_rating
from rentals.models import RENT, City
from rentals.tests import (
    get_test_owner, get_test_city, get_test_building, get_test_monthly_expense,
    get_test_rental)
from reservations.models import (
    ReservationLineItem, KNOWN_LINE_ITEM_NAMES, CONFIRMED, CANCELED)
from reservations.tests import (
    get_test_reservation, get_test_payment, get_test_refund,
    get_test_credit_card_fee, get_test_reservation_line_item)
from stats.models.computer import compute_stats, reservation_res_stats
from stats.models.getter import StatsGetter
from stats.models.stale import Stale
from stats.models.stats import DAY, MONTH
from util.channels import BOOKINGCOM, AIRBNB
from util.tests import TestCase
from util.timezone import str_to_tz_dt


def setup_computer_tests():
  """
  Rent / leases situation:
  Date, total rent / day, Long Beach rent / day, New York rent / day
  3/2   30                0                      30
  3/3   40                10                     30
  3/4   50                20                     30

  Profit situation:
  Date, Total revenue,Long Beach revenue,New York revenue
  3/2   0             0                  0
  3/3   50            0                  50
  3/4   100           50                 50
  3/5   50            50                 0
  """
  rent = KNOWN_LINE_ITEM_NAMES.RENT
  long_beach_owner = get_test_owner(username='TheQueenofFrance')
  long_beach_castle = get_test_building(
      city='Long Beach', owner=long_beach_owner, nickname='Long Beach Castle')
  long_beach = get_test_reservation(
      nickname='Long Beach Castle Dungeon',
      building=long_beach_castle,
      check_in='2018-03-04 16:00',
      check_out='2018-03-06 11:00',
      channel_id='long_beach_res',
      ideal_payin=Money(100.0, 'USD'))
  ReservationLineItem.objects.create(
      name=rent,
      value=Money(100.0, 'USD'),
      reservation=long_beach)
  Stale.objects.mark_stale_due_to_reservation(long_beach)
  # For the purposes of reporting, we pretend to pay the same rent daily
  # averaged out over the month. So it's, like, monthly rent / days in that
  # month. So it's a bit tricky picking test numbers that work out nice!
  # Luckily this test only runs on March which has 31 days. So if rent is
  # 310, daily rent is 10.

  # daily rent is 10.
  rent1 = get_test_monthly_expense(
      rental=long_beach.rental, start_date=date(2018, 3, 3),
      monthly_amount=Money(310, 'USD'), kind=RENT)
  Stale.objects.mark_stale_due_to_monthly_expense(rent1)
  # daily rent is 20.
  rent2 = get_test_monthly_expense(
      rental=long_beach.rental, start_date=date(2018, 3, 4),
      monthly_amount=Money(310 * 2, 'USD'), kind=RENT)
  Stale.objects.mark_stale_due_to_monthly_expense(rent2)

  # rent for inactive rentals shouldn't count.
  rent3 = get_test_monthly_expense(
      building=long_beach_castle, is_active=False,
      start_date=date(2018, 3, 1), monthly_amount=Money(310 * 2000, 'USD'),
      kind=RENT)
  Stale.objects.mark_stale_due_to_monthly_expense(rent3)

  new_york = get_test_reservation(
      city='New York',
      check_in='2018-03-03 16:00',
      check_out='2018-03-05 11:00',
      channel_id='new_york_res',
      nickname='Empire State Basement',
      ideal_payin=Money(100.0, 'USD'))
  ReservationLineItem.objects.create(
      name=rent,
      value=Money(100.0, 'USD'),
      reservation=new_york)
  Stale.objects.mark_stale_due_to_reservation(new_york)
  # daily rent is 30.
  rent4 = get_test_monthly_expense(
      rental=new_york.rental, start_date=date(2017, 1, 1),
      monthly_amount=Money(310 * 3, 'USD'), kind=RENT)
  Stale.objects.mark_stale_due_to_monthly_expense(rent4)
  Stale.objects.fix()


class ResStatsTests(TestCase):
  def test_no_revenue(self):
    res = get_test_reservation(
        check_in='2019-01-03 16:00', check_out='2019-01-04 11:00',
        channel=AIRBNB, guesty_id='whatever')
    get_test_reservation_line_item(
        name=KNOWN_LINE_ITEM_NAMES.RENT,
        value=Money(150.0, 'USD'),
        reservation=res)
    get_test_reservation_line_item(
        name=KNOWN_LINE_ITEM_NAMES.CLEANING_FEES,
        value=Money(100.0, 'USD'),
        reservation=res)
    get_test_reservation_line_item(
        name=KNOWN_LINE_ITEM_NAMES.HOST_CHANNEL_FEE,
        value=Money(-10.0, 'USD'),
        reservation=res)
    self.assertEqual(
        Money('0', 'USD'),
        res.get_likely_payin(nnow=str_to_tz_dt('2019-02-01')))
    self.assertEqual(Money('240', 'USD'), res.get_likely_balance_due())
    res_stats = reservation_res_stats(res)
    self.assertEqual(Decimal('0'), res_stats.cleaning_income)
    self.assertEqual(Decimal('0'), res_stats.channel_fees)
    self.assertEqual(Decimal('0'), res_stats.rooms_revenue)
    self.assertEqual(Decimal('0'), res_stats.revenue())

  def test_canceled_airbnb_host_channel_fee(self):
    """ Real life story.
    https://app.guesty.com/reservations/5af60150ae3e0505d9e5669a/guests
    This is really screwy. In the Guesty user interface it shows as
    accommodation fare $870
    cleaning fee $130
    host channel fee -$30
    accommodation fare adjustment -$130
    cleaning fee adjustment $0
    host channel fee adjustment $3.90
    Total payout $843.90
    But the line items are as set out below:
    """
    res = get_test_reservation(
        channel=AIRBNB, status=CANCELED,
        check_in=str_to_tz_dt('2019-01-01 16:00'),
        check_out=str_to_tz_dt('2019-01-02 11:00'),
        canceled_at=str_to_tz_dt('2018-10-16 12:00'),
        ideal_payin=Money(843.90, 'USD'))
    # Note that 843.90 = 740 + 130 - 26.1
    payment = get_test_payment(reservation=res, amount=Money('843.90', 'USD'))
    get_test_reservation_line_item(
        name='Accommodation fare',
        value=Money('740.00', 'USD'),
        reservation=res)
    # In Guesty, this remains unchanged as a line item but if you look at the
    # user interface you'll see that it's adjusted to 0.
    get_test_reservation_line_item(
        name='Cleaning fee',
        value=Money('130.00', 'USD'),
        reservation=res)
    # This started off as -$30 but when it was canceled there was an adjustment
    # on the channel fee of +$3.90
    get_test_reservation_line_item(
        name='Host channel fee',
        value=Money('-26.10', 'USD'),
        reservation=res)
    res_stats = reservation_res_stats(res)
    # Note that 740 + 130 + 26.1 = 896.1 which is the total amount the guest
    # got charged.
    self.assertEqual(
        round(Decimal(740 + 130), 2),
        res_stats.cancellation_fees)
    self.assertEqual(round(Decimal(26.1), 2), res_stats.channel_fees)

    payment.amount = Money('123.45', 'USD')
    payment.save()
    res.channel = BOOKINGCOM
    res.save()
    res._calc_actual_payin()
    res_stats = reservation_res_stats(res)
    self.assertEqual(round(Decimal(123.45), 2), res_stats.cancellation_fees)
    self.assertEqual(Decimal(0), res_stats.channel_fees)

  def test_likely_balance_due_applied_to_rooms_revenue(self):
    """ https://keys.hihoward.com/likely_payin_not_ideal_payin/ """
    res = get_test_reservation(
        channel=AIRBNB, status=CONFIRMED,
        check_in=str_to_tz_dt('2019-01-01 16:00'),
        check_out=str_to_tz_dt('2019-01-02 11:00'), guesty_id='whatever')
    get_test_reservation_line_item(
        name='Accommodation fare',
        value=Money('800.00', 'USD'),
        reservation=res)
    get_test_reservation_line_item(
        name='Cleaning fee',
        value=Money('50.00', 'USD'),
        reservation=res)
    get_test_payment(reservation=res, amount=Money('750', 'USD'))
    # $850 is due but we only received $750 so far. The rule is, any LIKELY
    # outstanding balance, positive or negative, gets applied to the
    # rooms_revenue. So for an Airbnb reservation, on the day of checkin the
    # LIKELY payin is equal to the IDEAL payin, regardless of the ACTUAL payin.
    res_stats = reservation_res_stats(res, nnow=str_to_tz_dt('2019-01-01'))
    self.assertEqual(Decimal('800'), res_stats.rooms_revenue)
    self.assertEqual(Decimal('50'), res_stats.cleaning_fees)
    # But the same situation a week later looks more bleak.
    res_stats = reservation_res_stats(res, nnow=str_to_tz_dt('2019-01-08'))
    self.assertEqual(Decimal('700'), res_stats.rooms_revenue)
    self.assertEqual(Decimal('50'), res_stats.cleaning_fees)

  def test_reservation_res_stats(self):
    reservation = get_test_reservation(
        ideal_payin=Money(200.0, 'USD'), actual_payin=Money(200.0, 'USD'))
    names = KNOWN_LINE_ITEM_NAMES
    ReservationLineItem.objects.create(
        name=names.RENT,
        value=Money(100.0, 'USD'),
        reservation=reservation)
    ReservationLineItem.objects.create(
        name=names.HOST_CHANNEL_FEE,
        value=Money(-10.0, 'USD'),
        reservation=reservation)
    ReservationLineItem.objects.create(
        name=names.CLEANING_FEE,
        value=Money(50.0, 'USD'),
        reservation=reservation)
    ReservationLineItem.objects.create(
        name=names.EARLY_CHECKIN,
        value=Money(60.0, 'USD'),
        reservation=reservation)

    charges_and_fees = reservation_res_stats(reservation)

    self.assertEqual(charges_and_fees.channel_fees, Decimal(10))
    # Revenue is every dollar the guest paid. Channel fees are taken out of the
    # the revenue. So DON'T include channel fees in revenue. If you want PAYIN,
    # the actual dollar amount that hits our bank account, then you would do
    # revenue -abs(channel fees).
    self.assertEqual(charges_and_fees.revenue(), Decimal('210'))
    self.assertEqual(charges_and_fees.rooms_revenue, Decimal('100'))
    self.assertEqual(charges_and_fees.cleaning_fees, Decimal('50'))
    self.assertEqual(charges_and_fees.upsell_income, Decimal(60))


class ComputeNPSTests(TestCase):
  def setUp(self):
    super().setUp()
    self.saigon = get_test_city(name='Saigon')
    self.building = get_test_building(city=self.saigon)
    get_test_rating(
        score=8,
        check_in=str_to_tz_dt('2018-11-13 16:00'),
        check_out=str_to_tz_dt('2018-11-14 11:00'))
    get_test_rating(
        score=8,
        check_in=str_to_tz_dt('2018-12-23 16:00'),
        check_out=str_to_tz_dt('2019-01-02 11:00'))
    get_test_rating(
        score=9,
        check_in=str_to_tz_dt('2018-12-24 16:00'),
        check_out=str_to_tz_dt('2019-01-02 11:00'))
    get_test_rating(
        score=10, building=self.building,
        check_in=str_to_tz_dt('2018-12-25 16:00'),
        check_out=str_to_tz_dt('2019-12-26 11:00'))
    get_test_rating(
        score=1,
        check_in=str_to_tz_dt('2018-12-25 16:00'),
        check_out=str_to_tz_dt('2019-01-02 11:00'))
    get_test_reservation(
        check_in=str_to_tz_dt('2018-12-23 16:00'),
        check_out=str_to_tz_dt('2019-01-02 11:00'))

  def test_by_month(self):
    statses = compute_stats(date(2018, 12, 1), date(2019, 1, 1), MONTH)
    self.assertEqual(1, len(statses))
    stats = statses[0]
    self.assertEqual(4, stats.total_nps_scores)
    self.assertEqual(2, stats.promoters)
    self.assertEqual(1, stats.detractors)

  def test_by_day(self):
    statses = compute_stats(date(2018, 12, 25), date(2018, 12, 26), DAY)
    self.assertEqual(1, len(statses))
    stats = statses[0]
    self.assertEqual(2, stats.total_nps_scores)
    self.assertEqual(1, stats.promoters)
    self.assertEqual(1, stats.detractors)

  def test_by_owner(self):
    stats = compute_stats(
        date(2018, 12, 1), date(2019, 1, 1), MONTH,
        owner_id=self.building.owner.id)[0]
    self.assertEqual(1, stats.total_nps_scores)
    self.assertEqual(1, stats.promoters)
    self.assertEqual(0, stats.detractors)

  def test_by_city(self):
    stats = compute_stats(
        date(2018, 12, 1), date(2019, 1, 1), MONTH,
        city=self.saigon)[0]
    self.assertEqual(1, stats.total_nps_scores)
    self.assertEqual(1, stats.promoters)
    self.assertEqual(0, stats.detractors)

  def test_by_building(self):
    stats = compute_stats(
        date(2018, 12, 1), date(2019, 1, 1), MONTH,
        building_id=self.building.id)[0]
    self.assertEqual(1, stats.total_nps_scores)
    self.assertEqual(1, stats.promoters)
    self.assertEqual(0, stats.detractors)


class ComputerTests(TestCase):
  def test_compute_stats(self):
    """
    Date, Long Beach rent / day, New York rent / day
    3/2   0                      30
    3/3   10                     30
    3/4   20                     30
    """
    setup_computer_tests()

    def test_points_in_total(points_in_total):
      self.assertEqual(3, len(points_in_total))
      # 0
      self.assertEqual(date(2018, 3, 2), points_in_total[0].from_date)
      self.assertEqual(DAY, points_in_total[0].interval)
      self.assertEqual(2, points_in_total[0].nights_available)
      self.assertEqual(0, points_in_total[0].nights_occupied)
      self.assertEqual(
          Decimal(0.0), points_in_total[0].revenue())
      self.assertEqual(Decimal(30), points_in_total[0].rent)
      # 1
      self.assertEqual(
          Decimal(50.0), points_in_total[1].revenue())
      self.assertEqual(date(2018, 3, 3), points_in_total[1].from_date)
      self.assertEqual(1, points_in_total[1].nights_occupied)
      self.assertEqual(Decimal(10 + 30), points_in_total[1].rent)
      # 2
      self.assertEqual(
          Decimal(100.0), points_in_total[2].revenue())
      self.assertEqual(date(2018, 3, 4), points_in_total[2].from_date)
      self.assertEqual(2, points_in_total[2].nights_occupied)
      self.assertEqual(Decimal(20 + 30), points_in_total[2].rent)

    test_points_in_total(
        compute_stats(date(2018, 3, 2), date(2018, 3, 5), DAY))
    test_points_in_total(
        StatsGetter().get_stats(date(2018, 3, 2), date(2018, 3, 5), DAY))

    long_beach = City.objects.get(name='Long Beach')
    city_points = compute_stats(
        date(2018, 3, 2), date(2018, 3, 5), DAY, city=long_beach)
    self.assertEqual(1, city_points[0].nights_available)
    self.assertEqual(Decimal(0), city_points[0].rent)
    self.assertEqual(Decimal(10), city_points[1].rent)
    self.assertEqual(Decimal(0.0), city_points[1].revenue())
    self.assertEqual(Decimal(50.0), city_points[2].revenue())

    long_beach_owner = User.objects.get(username='TheQueenofFrance')
    owner_points = compute_stats(
        date(2018, 3, 2), date(2018, 3, 5), DAY, owner_id=long_beach_owner.pk)
    self.assertEqual(1, owner_points[0].nights_available)
    self.assertEqual(Decimal(0), city_points[0].rent)
    self.assertEqual(Decimal(10), city_points[1].rent)
    self.assertEqual(Decimal(0.0), owner_points[1].revenue())
    self.assertEqual(Decimal(50.0), owner_points[2].revenue())

  def test_bookingcom_cancellation_fees(self):
    names = KNOWN_LINE_ITEM_NAMES
    rental = get_test_rental()
    confirmed = get_test_reservation(
        rental=rental, check_in=str_to_tz_dt('2018-05-15 16:00'),
        check_out=str_to_tz_dt('2018-05-16 11:00'), status=CONFIRMED,
        channel=BOOKINGCOM,
        ideal_payin=Money(200.0, 'USD'))
    ReservationLineItem.objects.create(
        name=names.RENT,
        value=Money(200.0, 'USD'),
        reservation=confirmed)
    get_test_payment(reservation=confirmed, amount=Money(200.0, 'USD'))
    canceled = get_test_reservation(
        rental=rental, check_in=str_to_tz_dt('2018-05-15 16:00'),
        check_out=str_to_tz_dt('2018-05-16 11:00'), status=CANCELED,
        canceled_at=str_to_tz_dt('2018-10-16 12:00'), channel=BOOKINGCOM,
        ideal_payin=Money(100.0, 'USD'))
    ReservationLineItem.objects.create(
        name=names.RENT,
        value=Money(100.0, 'USD'),
        reservation=canceled)
    payment = get_test_payment(
        reservation=canceled, amount=Money(50.0, 'USD'))
    get_test_refund(payment=payment, amount=Money(10.0, 'USD'))
    stats = compute_stats(
        date(2018, 5, 15), date(2018, 5, 16), DAY, rental_id=rental.pk)[0]
    # This is all the confirmed reservation.
    self.assertEqual(Decimal('200'), stats.rooms_revenue)
    self.assertEqual(Decimal('40'), stats.cancellation_fees)
    # Booking.com doesn't charge channel_fees on canceled reservations. So this
    # value reflects the 15% fee on the confirmed reservation.
    self.assertEqual(Decimal('30'), stats.channel_fees)


class ExpenseTester(TestCase):
  def test_days_of_the_month_expenses(self):
    rental = get_test_rental()
    get_test_expense(
        month=date(2018, 10, 1), amount=Money('310.0', 'USD'),
        amortize=DAYS_OF_THE_MONTH, building=rental.building)
    get_test_expense(
        month=date(2018, 10, 1), amount=Money('620.0', 'USD'),
        amortize=DAYS_OF_THE_MONTH, owner=rental.building.owner)

    building_day = compute_stats(
        date(2018, 9, 30), date(2018, 10, 2), DAY,
        building_id=rental.building.pk)
    self.assertEqual(2, len(building_day))
    self.assertEqual(Decimal('0.0'), building_day[0].expenses)
    self.assertEqual(Decimal('10.0'), building_day[1].expenses)
    building_month = compute_stats(
        date(2018, 9, 1), date(2018, 11, 1), MONTH,
        building_id=rental.building.pk)
    self.assertEqual(2, len(building_month))
    self.assertEqual(Decimal('0.0'), building_month[0].expenses)
    self.assertEqual(Decimal('310.0'), building_month[1].expenses)
    owner_day = compute_stats(
        date(2018, 9, 30), date(2018, 10, 2), DAY,
        owner_id=rental.building.owner.pk)
    self.assertEqual(Decimal('0.0'), owner_day[0].expenses)
    self.assertEqual(Decimal('30.0'), owner_day[1].expenses)
    owner_month = compute_stats(
        date(2018, 9, 1), date(2018, 11, 1), MONTH,
        owner_id=rental.building.owner.pk)
    self.assertEqual(2, len(owner_month))
    self.assertEqual(Decimal('0.0'), owner_month[0].expenses)
    self.assertEqual(Decimal('930.0'), owner_month[1].expenses)
    self.assertEqual(Decimal('930.0'), owner_month[1].total_expenses())
    # Building and owner expenses shouldn't show up on rental queries.
    self.assertEqual(Decimal('0.0'), compute_stats(
        date(2018, 10, 1), date(2018, 10, 2), DAY,
        rental_id=rental.pk)[0].expenses)

  def test_credit_card_fees(self):
    res = get_test_reservation()
    get_test_credit_card_fee(reservation=res, amount=Money('4.0', 'USD'))
    get_test_credit_card_fee(reservation=res, amount=Money('5.0', 'USD'))
    res_stats = reservation_res_stats(res)
    self.assertEqual(Decimal('9.0'), res_stats.credit_card_fees)
