from django.db import models


CLEANER = 'Cleaner'
CLEANING_INSPECTOR = 'Cleaning inspector'
MAINTENANCE = 'Maintenance'
STARTER_WORK_TYPES = (CLEANER, CLEANING_INSPECTOR, MAINTENANCE)


class WorkTypeManager(models.Manager):
  def create_work_types(self):
    for work_type_choice in STARTER_WORK_TYPES:
      self.get_or_create(name=work_type_choice)

  def get_work_type(self, name):
    work_type = self.filter(name=name).first()
    if work_type:
      return work_type
    self.create_work_types()
    return self.filter(name=name).first()


class WorkType(models.Model):
  name = models.CharField(max_length=50, unique=True)

  objects = WorkTypeManager()

  def __str__(self):
    return self.name
