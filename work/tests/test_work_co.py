from work.models.work_co import WorkCo
from util.random_string import random_string
from util.tests import get_test_user


def get_test_work_co(**kwargs):
  owner = kwargs.get('owner', None)
  if not owner:
    owner = get_test_user(**kwargs)
  default_name = 'Bob {}s Cleaning Company'.format(random_string())
  return WorkCo.objects.create(
      name=kwargs.get('name', default_name),
      owner=owner,
      alerts_email=kwargs.get('alerts_email', 'alert@work_co.com'),
      services_tax_rate=kwargs.get('services_tax_rate', 10))
