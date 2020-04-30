from collections import namedtuple

from django.db import connection

from util.table import Table, Cell
from xxero.models.transactions import LineItem


CoconutData = namedtuple(
    'CoconutData', 'building_id coconut_id transaction_id line_item_id amount')


def get_coconut_datas(from_date, to_date, coconut_id=None, building_id=None):
  """ This is basically a single database query to pull back which transactions
  have which line items. It's useful both for the top level cash basis report,
  and for coconut details.

  [CoconutData, CoconutData, ...] """
  # The query pulls back stuff even for inactive buildings.
  with connection.cursor() as cursor:
    query = """
        SELECT tro.building_id, li.coconut_id, t.id, li.id, li.amount
        FROM xxero_transaction AS t
        JOIN xxero_lineitem AS li ON t.id = li.transaction_id
        JOIN xxero_lineitem_tracking_options AS lito
            ON li.id = lito.lineitem_id
        JOIN xxero_trackingoption AS tro ON lito.trackingoption_id = tro.id
        WHERE t.when >= %s AND t.when < %s
        AND tro.building_id IS NOT NULL
        AND li.coconut_id IS NOT NULL """
    args = [from_date, to_date]
    if coconut_id:
      query += 'AND li.coconut_id = %s '
      args.append(coconut_id)
    if building_id:
      query += 'AND tro.building_id = %s '
      args.append(building_id)
    query += 'ORDER BY t.id, li.id;'

    cursor.execute(query, args)

    for row in cursor.fetchall():
      yield(CoconutData(*row))


def get_building_coconut_transactions_table(
    from_date, to_date, coconut_id, building_id):
  """ We want to see the whole transaction and other line items, a.k.a.
  context, not just the line items with the coconut in question. """
  datas = list(get_coconut_datas(from_date, to_date, coconut_id, building_id))
  transaction_ids = set([data.transaction_id for data in datas])
  line_items = LineItem.objects.filter(
      transaction__pk__in=transaction_ids).select_related(
          'transaction', 'transaction__bank_account',
          'transaction__contact', 'coconut').order_by(
              '-transaction__when', 'transaction__pk', 'pk')
  current_transaction = None
  current_line_items = []
  table = Table([
      'Transaction', 'Contact', 'Reference', 'When', 'Transaction amount',
      'Line item amount', 'Coconut code', 'Coconut name'])
  for line_item in line_items:
    if not current_transaction or current_transaction != line_item.transaction:
      if current_transaction:
        _add_to_table(
            current_transaction, current_line_items, coconut_id, table)
      current_transaction = line_item.transaction
      current_line_items = []
    current_line_items.append(line_item)
  if current_transaction:
    _add_to_table(
        current_transaction, current_line_items, coconut_id, table)
  return table


def _add_to_table(
    transaction, line_items, coconut_id_in_question, table):

  bank_transaction_id_cell = Cell(
      str(transaction.bank_transaction_id), url=transaction.admin_url())
  contact_name = '(no contact)'
  if transaction.contact:
    contact_name = transaction.contact.name
  table.create_row([
      bank_transaction_id_cell, contact_name,
      transaction.reference or '', transaction.when, transaction.amount, '',
      '', ''])
  for line_item in line_items:
    coconut_name = '(no coconut)'
    coconut_code = ''
    if line_item.coconut:
      coconut_name = line_item.coconut.name
      coconut_code = line_item.coconut.code
    table.create_row([
        '', '', '', '', '', line_item.amount, coconut_code, coconut_name])
