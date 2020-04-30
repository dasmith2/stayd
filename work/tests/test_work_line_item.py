from djmoney.money import Money

from work.models.work_line_item import WorkLineItem
from work.tests.test_cleaning import get_test_cleaning


def get_test_work_line_item(**kwargs):
  work = kwargs.get('work', None)
  if not work:
    work = get_test_cleaning(**kwargs)
  return WorkLineItem.objects.create(
      work=work,
      amount=kwargs.get('amount', Money('10', 'USD')),
      description=kwargs.get('description', 'Fixed the couch'),
      charge_sales_tax=kwargs.get('charge_sales_tax', True))
