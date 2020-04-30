from functools import wraps

from util.views import message


ACCOUNTANT = 'accountant'
CLEANING_ADMINISTRATOR_GROUP = 'cleaning_administrator'
VIRTUAL_HOST_GROUP = 'virtual_host'
CSV_UPLOAD = 'csv_upload'


def is_superuser(function):
  def wrap(request, *args, **kwargs):
    if request.user.is_superuser:
      return function(request, *args, **kwargs)
    return message('Permission denied', 'You need to be a superuser.', 403)
  return wrap


def user_can_groups(user, *group_names):
  """ if user_can_groups(request.user, ACCOUNTANT): ...
  Superusers, while technically not in groups for the most part, can
  nevertheless act as any group, hence the name "can_group"
  a.k.a. "can act as group". """
  return user.is_superuser or user_in_groups(user, *group_names)


def user_in_groups(user, *group_names):
  """ if user_in_groups(request.user, ACCOUNTANT): ... """
  return user.groups.filter(name__in=group_names).exists()


def can_groups(*group_names):
  """
  @login_required
  @can_groups(ACCOUNTANT)
  def do_request(request):
    ...
  """
  def _check_groups(function):
    @wraps(function)
    def wrap(request, *args, **kwargs):
      if request.user.is_superuser:
        return function(request, *args, **kwargs)
      if request.user.groups.filter(name__in=group_names).exists():
        return function(request, *args, **kwargs)
      if len(group_names) == 0:
        raise Exception('You didnt specify any groups.')
      elif len(group_names) == 1:
        text = 'You need to be in the {} group.'.format(group_names[0])
      elif len(group_names) == 2:
        text = 'You need to be in the {} or {} group.'.format(*group_names)
      else:
        text = 'You need to be in the {}, or {} group.'.format(
            ', '.join(group_names[:-1]), group_names[-1])
      return message('Permission denied', text, 403)
    return wrap
  return _check_groups
