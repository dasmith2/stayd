from work.models.work_co_worker import WorkCoWorker
from work.models.work_type import WorkType
from work.tests.test_work_co import get_test_work_co
from work.tests.test_worker import set_worker_stuff


def get_test_work_co_worker(**kwargs):
  WorkType.objects.create_work_types()
  work_co = kwargs.get('work_co', None)
  if not work_co:
    work_co = get_test_work_co(**kwargs)
  worker = WorkCoWorker(
      work_co=work_co,
      active=kwargs.get('active', True),
      internal_notes=kwargs.get('internal_notes', ''))
  set_worker_stuff(worker, **kwargs)
  return worker
