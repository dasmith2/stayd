from collections import namedtuple
from datetime import date

from django.conf import settings
from django.db.models import Q
from django.urls import reverse

from stats.models.computer import reservation_res_stats, get_pro_rated_fraction
from rentals.models import Rental
from reservations.models import Reservation


ResDeets = namedtuple(
    'ResDeets', 'res_deets_list revenue_headers expense_headers')


_res_deets_fields = [
    'admin_url',
    'guesty_id',
    'stayd_web_url',
    'stayd_web_id',
    'guest_name',
    'check_in',
    'check_out',
    'nights',
    'nights_in_range',
    'fraction_of_a_combo',
    'fraction_of_a_combo_description',
    'revenue_details',
    'prepayment',
    'prepayment_date',
    'expense_details']


class ResDeetsForList(namedtuple('ResDeetsForList', _res_deets_fields)):
  def revenue_detail(self, header):
    for name, amount in self.revenue_details:
      if header == name:
        return amount
    return ''

  def expense_detail(self, header):
    for name, amount in self.expense_details:
      if header == name:
        return amount
    return ''


def get_all_res_deets(from_date, to_date, rental_id=None, building_id=None):
  """ Sometimes the accountants will pull back a reservation list for a whole
  year, so this list can get a little long, hence the performance
  improvements. """
  if int(bool(rental_id)) + int(bool(building_id)) != 1:
    raise Exception('Specify exactly one of rental_id or building_id')
  from_date = from_date
  to_date = to_date
  reservations = Reservation.objects.reservations_in_range(
      from_date, to_date).select_related(
          'rental', 'rental__building', 'guest', 'guestyreservation')
  rental = None
  if rental_id:
    rental = Rental.objects.get(pk=rental_id)
    reservations = reservations.filter(
        Q(rental=rental) | Q(rental__is_combo_of=rental))
  elif building_id:
    reservations = reservations.filter(rental__building_id=building_id)

  res_deets_list = []
  revenue_headers_set = set()
  expense_headers_set = set()
  for reservation in reservations:
    res_deets_for_list = get_res_deets_for_list(
        from_date, to_date, reservation, rental or reservation.rental)
    if res_deets_for_list:
      _add_headers(revenue_headers_set, res_deets_for_list.revenue_details)
      _add_headers(expense_headers_set, res_deets_for_list.expense_details)
      res_deets_list.append(res_deets_for_list)

  return ResDeets(
      res_deets_list, sorted(list(revenue_headers_set)),
      sorted(list(expense_headers_set)))


def get_res_deets_for_list(from_date, to_date, reservation, rental):
  res_stats = reservation_res_stats(reservation)

  pro_rated_fraction_by_days = get_pro_rated_fraction(
      reservation, from_date, to_date)
  fraction_of_a_combo = reservation.attributed_to_rental(rental)

  total_and_within = reservation.total_and_within(from_date, to_date)
  # By design, reservations_in_range potentially pulls back reservations
  # that are just outside the given range.
  if total_and_within[1] > 0:
    # There might not be a guesty_reservation, as is the case with the old
    # booking.com reservations we manually imported.
    admin_url = None
    guesty_id = None
    try:
      guesty_reservation = reservation.guestyreservation
      admin_url = guesty_reservation.admin_url()
      guesty_id = guesty_reservation.guesty_id
    except Reservation.guestyreservation.RelatedObjectDoesNotExist:
      pass
    stayd_web_url = reverse(
        'reservation_history', kwargs={'pk': reservation.pk})

    prepayment = reservation.prepayment()
    revenue = res_stats.revenue()
    total_expenses = res_stats.total_expenses()
    prepayment_date = None
    if prepayment:
      prepayment_date = prepayment.paid_at.date()
      if prepayment_date == date(2018, 1, 1):
        prepayment_date = 'Unknown date'
    revenue_details = res_stats.describe_revenue(
        pro_rated_fraction_by_days * fraction_of_a_combo)
    expense_details = res_stats.describe_expenses(
        pro_rated_fraction_by_days * fraction_of_a_combo)
    nights_in_range = pro_rated_fraction_by_days * res_stats.nights_occupied
    fraction_of_a_combo_description = ''
    if fraction_of_a_combo != 1.0:
      fraction_of_a_combo_description = '{} is {}% of {}'.format(
          rental.nickname, round(100 * fraction_of_a_combo),
          reservation.rental.nickname)
    if revenue or total_expenses:
      return ResDeetsForList(
          admin_url=admin_url,
          guesty_id=guesty_id,
          stayd_web_url=stayd_web_url,
          stayd_web_id=reservation.pk,
          guest_name=reservation.guest.get_name(),
          check_in=reservation.check_in,
          check_out=reservation.check_out,
          nights=res_stats.nights_occupied,
          nights_in_range=nights_in_range,
          fraction_of_a_combo=fraction_of_a_combo,
          fraction_of_a_combo_description=fraction_of_a_combo_description,
          revenue_details=revenue_details,
          prepayment=prepayment and prepayment.amount.amount,
          prepayment_date=prepayment_date,
          expense_details=expense_details)


def _add_headers(add_headers_to, description):
  for name, amount in description:
    add_headers_to.add(name)


def get_all_res_deets_for_csv(
    from_date, to_date, rental_id=None, building_id=None, include_guests=True):
  all_res_deets = get_all_res_deets(
      from_date, to_date, rental_id=rental_id, building_id=building_id)
  rows = []
  # This WOULD be an exact copy of reports/templates/reservation_list.html
  # except that it has to flatten a few nested tables.
  header_row = []
  if include_guests:
    header_row.extend([
        'Guesty ID',
        'StaydWeb ID',
        'Guest'])
  header_row.extend([
      'Check in',
      'Check out',
      'Nights',
      'Pro rated nights',
      'Combo rental fraction'])
  for revenue_header in all_res_deets.revenue_headers:
    header_row.append(revenue_header)
  header_row.extend(['Prepayment', 'Prepayment date'])
  for expense_header in all_res_deets.expense_headers:
    header_row.append(expense_header)
  rows.append(header_row)
  for res_deets in all_res_deets.res_deets_list:
    res_row = []
    if include_guests:
      res_row.extend([
          res_deets.admin_url, settings.KEYS_SERVER + res_deets.stayd_web_url,
          res_deets.guest_name])
    res_row.extend([
        res_deets.check_in,
        res_deets.check_out,
        res_deets.nights,
        res_deets.nights_in_range,
        res_deets.fraction_of_a_combo])
    for revenue_header in all_res_deets.revenue_headers:
      res_row.append(res_deets.revenue_detail(revenue_header))
    if res_deets.prepayment:
      res_row.extend([
          res_deets.prepayment, res_deets.prepayment_date])
    else:
      res_row.extend(['', ''])
    for expense_header in all_res_deets.expense_headers:
      res_row.append(res_deets.expense_detail(expense_header))
    rows.append(res_row)
  return rows
