from django.conf import settings


def can_read_net():
  if settings.TEST:
    raise Exception(
        'Tests should run fast and work offline, so you can\'t do network '
        'calls in tests.')
  elif settings.RUNSERVER:
    raise Exception(
        'Network calls are unpredictably slow and the website should always '
        'go fast. You should probably put this network call in a @background '
        'thread.')
  return True


def can_write_net():
  can_read_net()
  if not settings.PROD:
    raise Exception(
        'Only production is allowed to write over the network.')
  return True
