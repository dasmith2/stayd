""" I think this used to be an important abstraction from the Properly days.
These days it feels a little redundant. """
import re

from django.db import models

from rentals.models import Rental
from work.models.rental import ProperlyRental
from util.random_string import get_new_random_string
from util.timezone import now


def get_checklist_id_from_url(url):
  searched = re.compile(r'checklists/([\w]+)/[\w]+/').search(url)
  if searched:
    return searched.groups()[0]


class MaintenanceChecklist(models.Model):
  """ Checklists don't get a source checklist id for some reason, which is fine
  by me because the whole source_<whatever>_id pattern is a totally unnecessary
  complication. But taskGroups and tasks DO get a source_<whatever>_id. Who
  designed this API.

  If we ever build our own of these, DON'T require a rental. The team would
  love to be able to apply the same checklist to multiple rentals for obvious
  reasons. """
  properly_rental = models.ForeignKey(  # Goes away
      ProperlyRental, on_delete=models.CASCADE, null=True, blank=True)
  rental = models.ForeignKey(  # New
      Rental, on_delete=models.CASCADE, null=True, blank=True)
  title = models.CharField(max_length=200)
  description = models.TextField(blank=True, default='')
  unique_prefix = models.CharField(
      max_length=20, default=get_new_random_string, help_text=(
          'Helpful for giving source_whatever_ids to things.'))
  checklist_id = models.CharField(
      max_length=100, null=True, blank=True, db_index=True, help_text=(
          'This comes back in the response to the create_checklist request. '
          'You need it to create an update request.'))
  created_at = models.DateTimeField(auto_now_add=True)
  disabled_at = models.DateTimeField(null=True, blank=True)

  def save(self, *args, **kwargs):
    if self.properly_rental:
      self.rental = self.properly_rental.rental
    super().save(*args, **kwargs)

  def __repr__(self):
    return '<MaintenanceChecklist{}: {}>'.format(self.pk, self.title)

  def create_checklist_data(self):
    """
    Someday, if Properly ever gets their bugs fixed, we'll be able to include
    one taskGroup/slide per task, something like {
    'sourceTaskGroupId': 'qwot',
    'title': 'Pictures in this group',
    'verificationRequired': True,
    'sourcePictureUrl': 'http://keys.hihoward.com/static/fake_cc.jpg'}
    """
    tasks = []
    for task in self.checklistitem_set.order_by('source_task_id'):
      tasks.append({'sourceTaskId': task.source_task_id, 'label': task.label})
    return {
        'sourcePropertyId': self.properly_rental.get_source_property_id(),
        'title': self.title,
        'description': self.description or self.title,  # Required field.
        'taskGroups': [{
            'sourceTaskGroupId': self.unique_prefix,
            'title': 'Tasks',
            'verificationRequired': True,
            'tasks': tasks}]}

  def add_task(self, label):
    source_task_id = '{}{}'.format(
        self.unique_prefix, self.checklistitem_set.count() + 1)
    ChecklistItem.objects.create(
        checklist=self, source_task_id=source_task_id, label=label)

  def create_checklist(self, api):
    if self.checklist_id:
      raise Exception(
          'If you create a checklist that\'s already created you\'ll get '
          'duplicates.')
    if not self.checklistitem_set.exists():
      raise Exception('You cant create an empty checklist on Properly')
    send_data = self.create_checklist_data()
    created_json = api.checklist_create(send_data)
    if 'checklist.create' in created_json:
      self.checklist_id = created_json['checklist.create'][0]['checklistId']
      self.save()
      return created_json
    else:
      raise Exception('checklist not created.', send_data, created_json)

  def disable(self, api):
    if api.checklist_disable(self.checklist_id).ok:
      self.disabled_at = now()
      self.save()
    return self


class ChecklistItem(models.Model):
  checklist = models.ForeignKey(MaintenanceChecklist, on_delete=models.CASCADE)
  source_task_id = models.CharField(max_length=20, help_text=(
      'We pick this ID, and send it along on create and update checklist '
      'requests.'))
  label = models.TextField(help_text='A description of what needs to be done.')

  class Meta:
    ordering = ('pk',)

  def __repr__(self):
    return '<ChecklistItem{}: {}>'.format(self.pk, self.label)
