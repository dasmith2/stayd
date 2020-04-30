from work.models.work_type import WorkType, CLEANER


def get_test_work_type(**kwargs):
  name = kwargs.get('name', CLEANER)
  existing = WorkType.objects.filter(name=name).first()
  if existing:
    return existing
  return WorkType.objects.create(name=name)
