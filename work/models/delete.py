""" These are tools for forcibly deleting things for web tests. """
from django.conf import settings

from work.models.cleaning_checklist import CleaningChecklist


def not_prod(function):
  def wrap(*args, **kwargs):
    if settings.PROD:
      raise Exception('Dont call this function in production!')
    return function(*args, **kwargs)
  return wrap


@not_prod
def delete_all_cleaning_checklists():
  for cleaning_checklist in CleaningChecklist.objects.all():
    delete_cleaning_checklist(cleaning_checklist)


@not_prod
def delete_cleaning_checklist(cleaning_checklist):
  for cleaning_config in cleaning_checklist.cleaningconfig_set.all():
    delete_cleaning_config(cleaning_config)
  cleaning_checklist.delete()


@not_prod
def delete_cleaning_config(cleaning_config):
  if cleaning_config:
    cleaning_config.delete()


@not_prod
def delete_worker(worker):
  for work in set(worker.accepted_by.all()) | set(worker.offered_to.all()):
    work.get_child_class_instance().delete()
  worker.delete()


@not_prod
def delete_cleaning(cleaning):
  if cleaning:
    cleaning.worklineitem_set.all().delete()
    cleaning.delete()


@not_prod
def delete_building(building):
  if building:
    for rental in building.rental_set.all():
      for cleaning in rental.cleaning_set.all():
        delete_cleaning(cleaning)
      rental.reservation_set.all().delete()
      rental.ticket_set.all().delete()
      rental.delete()
    building.delete()


@not_prod
def delete_maintenance(maintenance):
  if maintenance:
    maintenance.ticket_set.all().delete()
    maintenance.delete()
