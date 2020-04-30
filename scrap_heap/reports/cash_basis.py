from collections import namedtuple
from decimal import Decimal

from django.db.models import Sum
from django.shortcuts import reverse
from djmoney.money import Money

from rentals.models import Building
from reports.cash_basis.coconut import get_coconut_datas
from reports.cash_basis.revenue import get_payments, get_refunds
from util.table import Table, Cell
from util.urls import date_to_url_str
from xxero.models.coconuts import Coconut


def get_cash_basis_table(from_date, to_date):
  # One column per building. One row per coconut.
  headers = ['']
  buildings = Building.objects.filter(is_active=True).order_by('nickname')
  for building in buildings:
    headers.append(building.nickname)
  table = Table(headers, blank_td_text='-')

  _append_payment_refund_rows(table, buildings, from_date, to_date)
  _append_coconut_rows(table, buildings, from_date, to_date)

  return table


PaymentsRefunds = namedtuple('PaymentsRefunds', 'building payments refunds')


def _append_payment_refund_rows(table, buildings, from_date, to_date):
  payment_refund_lookup = _payment_refund_lookup(
      buildings, from_date, to_date)
  payment_row = table.create_row([Cell('Payments', is_header=True)])
  refund_row = table.create_row([Cell('Refunds', is_header=True)])
  for building in buildings:
    payment_refund = payment_refund_lookup[building.pk]
    url_kwargs = {
        'from_date_str': date_to_url_str(from_date),
        'to_date_str': date_to_url_str(to_date), 'building_id': building.pk}
    payment_url = reverse('revenue_details', kwargs=url_kwargs)
    refund_url = reverse('refund_details', kwargs=url_kwargs)
    if payment_refund.payments:
      payment_row.add(Cell(str(payment_refund.payments), url=payment_url))
    else:
      payment_row.add('')
    if payment_refund.refunds:
      refund_row.add(Cell(str(payment_refund.refunds), url=refund_url))
    else:
      refund_row.add('')


def _payment_refund_lookup(buildings, from_date, to_date):
  """ {building_id ->
           PaymentsRefunds(building, Money(123.32), Money(43.2)),
       ... } """

  payment_lookup = {}
  pay_building_column = 'reservation__rental__building_id'
  # This does, like, <QuerySet [{'reservation__rental__building_id': 27,
  # 'total': Decimal('37165.06')}, ...]>
  for data in get_payments(from_date, to_date).values(
      pay_building_column).annotate(total=Sum('amount')):
    payment_lookup[data[pay_building_column]] = data['total']

  refund_lookup = {}
  refund_building_column = 'payment__reservation__rental__building_id'
  for data in get_refunds(from_date, to_date).values(
      refund_building_column).annotate(total=Sum('amount')):
    refund_lookup[data[refund_building_column]] = data['total']

  to_return = {}
  for building in buildings:
    payments = Money(payment_lookup.get(building.pk, Decimal('0')), 'USD')
    refunds = Money(refund_lookup.get(building.pk, Decimal('0')), 'USD')
    to_return[building.pk] = PaymentsRefunds(building, payments, refunds)
  return to_return


def _append_coconut_rows(table, buildings, from_date, to_date):
  # One row per coconut
  expense_lookup, coconuts = _coconut_lookup(from_date, to_date)
  coconut_row_lookup = {}
  for coconut in coconuts:
    coconut_row_lookup[coconut] = table.create_row(
        [Cell(coconut.name, is_header=True)])

  for building in buildings:
    buildings_coconuts = expense_lookup.get(building, None)
    for coconut in coconuts:
      use_value = Money('0', 'USD')
      if buildings_coconuts:
        use_value = buildings_coconuts.get(coconut, use_value)
      detail_url = reverse('coconut_details', kwargs={
          'from_date_str': date_to_url_str(from_date),
          'to_date_str': date_to_url_str(to_date), 'coconut_id': coconut.pk,
          'building_id': building.pk})
      if use_value:
        coconut_row_lookup[coconut].add(
            Cell(str(use_value), url=detail_url))
      else:
        coconut_row_lookup[coconut].add('')


def _coconut_lookup(from_date, to_date):
  """
  {building -> {Coconut(661): $12.3, Coconut(772): -$32.1}, ...},
  [Coconut(661), Coconut(772), ...]
  """
  lookup = {}
  coconuts = set()

  building_lookup = dict([
      (building.pk, building) for building in Building.objects.all()])
  coconut_lookup = dict([
      (coconut.pk, coconut) for coconut in Coconut.objects.all()])
  for coconut_data in get_coconut_datas(from_date, to_date):
    # The query pulls back stuff even for inactive buildings.
    if coconut_data.building_id in building_lookup:
      building = building_lookup[coconut_data.building_id]
      coconut = coconut_lookup[coconut_data.coconut_id]
      if building not in lookup:
        lookup[building] = {}
      if coconut not in lookup[building]:
        lookup[building][coconut] = Money('0', 'USD')
      lookup[building][coconut] += Money(coconut_data.amount, 'USD')
      coconuts.add(coconut)
  return lookup, sorted(list(coconuts), key=lambda x: x.name)
