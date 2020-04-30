from unittest.mock import Mock, call

from work.api import API
from work.api_examples import CHECKLIST_CREATE
from work.models.maintenance_checklist import MaintenanceChecklist
from work.tests.test_rental import get_test_properly_rental
from util.tests import TestCase


def get_test_maintenance_checklist(**kwargs):
  properly_rental = kwargs.get('properly_rental', None)
  if 'properly_rental' not in kwargs:
    properly_rental = get_test_properly_rental(**kwargs)

  checklist = MaintenanceChecklist(
      properly_rental=properly_rental,
      title=kwargs.get('title', 'Big bad title here folks'),
      description=kwargs.get('description', 'Tiny little description.'),
      checklist_id=kwargs.get('checklist_id', None),
      disabled_at=kwargs.get('disabled_at', None))

  # The default is a random string, so just don't set the unique_prefix if none
  # was included.
  unique_prefix = kwargs.get('unique_prefix', None)
  if unique_prefix:
    checklist.unique_prefix = unique_prefix

  checklist.save()
  for item in kwargs.get('items', []):  # List of string labels
    checklist.add_task(item)
  return checklist


class ChecklistTests(TestCase):
  def test_create_checklist(self):
    properly_rental = get_test_properly_rental(
        properly_property_id='blarfindorp',
        source_property_id='blarfindorp')
    checklist = get_test_maintenance_checklist(
        properly_rental=properly_rental, title='Armies of comies',
        description='Life is long and often boring.', unique_prefix='ASDF')
    checklist.add_task('Glue the arms on the manikins')
    checklist.add_task('Poke the real live uncaged bear with a stick.')

    api = Mock(spec=API)
    api.checklist_create.return_value = CHECKLIST_CREATE

    checklist.create_checklist(api)

    checklist.refresh_from_db()
    self.assertEqual('5c104002e5fcd6b2df8f0480', checklist.checklist_id)

    expected = {
        'sourcePropertyId': 'blarfindorp',
        'title': 'Armies of comies',
        'description': 'Life is long and often boring.',
        'taskGroups': [{
            'sourceTaskGroupId': 'ASDF',
            'title': 'Tasks',
            'verificationRequired': True,
            'tasks': [
                {'sourceTaskId': 'ASDF1', 'label': (
                    'Glue the arms on the manikins')},
                {'sourceTaskId': 'ASDF2', 'label': (
                    'Poke the real live uncaged bear with a stick.')}]}]}
    self.assertEqual([call(expected)], api.checklist_create.call_args_list)
