from django.conf import settings


class CantUseTheNet(Exception):
  pass


def can_read_net():
  if settings.TEST:
    raise CantUseTheNet(
        'Tests should run fast and work offline, so you can\'t do network '
        'calls in tests.')
  elif settings.RUNSERVER:
    raise CantUseTheNet(
        'Network calls are unpredictably slow and the website should always '
        'go fast. You should probably put this network call in a @background '
        'thread.')
  return True


def can_write_net():
  can_read_net()
  if not settings.PROD:
    raise CantUseTheNet(
        'Only production is allowed to write over the network.')
  return True
