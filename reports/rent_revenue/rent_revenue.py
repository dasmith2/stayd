from django.template.defaultfilters import floatformat
from django.urls import reverse

from rentals.models import Building, Rental
from stats.models.getter import StatsGetter
from stats.models.stats import Stats, TOTAL
from util.table import Table, Cell
from util.templatetags.util_extras import currency
from util.urls import date_to_url_str


def get_rent_revenues_table(from_date, to_date, owner_id):
  headers = [
      '', 'Net', 'Revenue', 'Total expenses', 'Market rent', 'Cleaning income',
      'Channel fees', 'Taxes', 'Credit card fees', 'Cancellation fees',
      'Bento charges', 'ADR', 'Occupancy rate', 'RevPAR', 'Reservations',
      'Total occupied nights']
  table = Table(headers, classes=['results'])
  for rent_revenue in get_rent_revenues(from_date, to_date, owner_id):
    name_cell = Cell(
        rent_revenue.name, is_header=True, url=rent_revenue.url,
        classes=['indent_{}'.format(rent_revenue.indent)])
    table.create_row(cells=[
        name_cell,
        currency(rent_revenue.net()),
        currency(rent_revenue.revenue()),
        currency(rent_revenue.total_expenses()),
        currency(rent_revenue.rent),
        currency(rent_revenue.cleaning_fees),
        currency(rent_revenue.channel_fees),
        currency(rent_revenue.taxes),
        currency(rent_revenue.credit_card_fees),
        currency(rent_revenue.cancellation_fees),
        currency(rent_revenue.expenses),
        currency(rent_revenue.adr()),
        rent_revenue.occupancy_rate(),
        currency(rent_revenue.rev_par()),
        floatformat(rent_revenue.reservation_count),
        rent_revenue.nights_occupied])
  return table


def get_rent_revenues(from_date, to_date, owner_id):
  """ This returns one "Total" RentRevenue, one for each city, and one for
  each rental.

  to_date is exclusive. So if you want to query about march you do
  3/1/2018 through 4/1/2018. Note that this is different from the user
  interface, and that the view adds a day to to_date, making the user
  interface to_date inclusive. So in the user interface you'd do
  3/1/2018 through 3/.../2018 see I'm not even sure. How many days are in
  March? But with the calendar it's easy. You just pick the last day of
  the month. """
  total = RentRevenue('Total', 0, sort_key='')
  by_city = {}
  by_building = {}
  by_rental = {}

  _add_stats(
      from_date, to_date, owner_id, total, by_city, by_building,
      by_rental)

  return _merge_rent_revenues(total, by_city, by_building, by_rental)


def _add_stats(
    from_date, to_date, owner_id, total, by_city, by_building, by_rental):
  # This does one select per building, one select per rental. That's PRETTY
  # rad, but this ought to do the whole darn table in a single query.

  rentals = Rental.objects.filter(
      is_active=True, is_test_rental=False, combo_unit_description='')
  # You have to do distinct otherwise Django does a naive query where it
  # returns one building per non test rental.
  buildings = Building.objects.filter(
      is_active=True, rental__is_test_rental=False).distinct()
  if owner_id:
    rentals = rentals.filter(building__owner__pk=owner_id)
    buildings = buildings.filter(owner__pk=owner_id)

  getter = StatsGetter()

  for building in buildings:
    stats = getter.get_stats(
        from_date, to_date, TOTAL, building_id=building.pk)

    total.add(stats, include_0_occupancy=False)

    city = building.city.name
    if city not in by_city:
      by_city[city] = RentRevenue(city, 1, sort_key=city)
    by_city[city].add(stats, include_0_occupancy=False)

    nickname = building.nickname
    sort_key = '{} {}'.format(city, nickname)
    by_building[nickname] = RentRevenue(nickname, 2, sort_key)
    by_building[nickname].url = reverse('building_reservation_list', kwargs={
        'building_id': building.pk,
        'from_date_str': date_to_url_str(from_date),
        'to_date_str': date_to_url_str(to_date)})
    by_building[nickname].add(stats, include_0_occupancy=False)

  for rental in rentals:
    stats = getter.get_stats(from_date, to_date, TOTAL, rental_id=rental.pk)

    nickname = rental.nickname
    sort_key = '{} {} {}'.format(
        rental.building.city, rental.building.nickname, nickname)
    by_rental[nickname] = RentRevenue(nickname, 3, sort_key)
    by_rental[nickname].url = reverse('rental_reservation_list', kwargs={
        'rental_id': rental.pk,
        'from_date_str': date_to_url_str(from_date),
        'to_date_str': date_to_url_str(to_date)})
    by_rental[nickname].add(stats, include_0_occupancy=False)


def _merge_rent_revenues(total, by_city, by_building, by_rental):
  rent_revenues = [total] + list(by_city.values()) + (
      list(by_building.values()) + list(by_rental.values()))
  rent_revenues.sort(key=lambda rr: rr.sort_key)
  return rent_revenues


class RentRevenue(Stats):
  """ This keeps track of rent and revenue for something, be it a single rental
  or a whole city. It also includes some display information suitable for
  the rent revenue report. """
  def __init__(self, name, indent, sort_key):
    super(RentRevenue, self).__init__()
    self.name = name
    self.indent = indent
    self.sort_key = sort_key
    self.url = None

  def __repr__(self):
    return 'RentRevenue({}, {}, {})'.format(
        self.name, self.indent, self.sort_key)
