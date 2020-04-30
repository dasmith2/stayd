from django.http import JsonResponse, HttpRequest


OK = {'OK': True}
OK_RESPONSE = JsonResponse(OK)


def ajax(function):
  """ A decorator for views that will return
  JsonResponse({'problem': 'Things bad!'}) when the view
  raises AjaxProblem('Things bad!') If the view returns data, return
  JsonResponse(data). If the view returns a JsonResponse, simply return the
  JsonResponse. """
  def wrap(request, *args, **kwargs):
    try:
      response = function(request, *args, **kwargs)
      if isinstance(response, JsonResponse):
        return response
      return JsonResponse(response)
    except AjaxProblem as ex:
      return ex.get_problem_response()
  return wrap


class AjaxProblem(Exception):
  def __init__(self, *args, **kwargs):
    self.message = args[0]
    super().__init__(*args, **kwargs)

  def get_problem_response(self):
    return problem_response(self.message)


def problem_response(message, status_code=200):
  return JsonResponse({'problem': message}, status=status_code)


def get_ajax_variable(data, variable_name, required=True):
  """ data can be a dictionary such as request.POST, or it can just be a
  request. """
  if isinstance(data, HttpRequest):
    data = get_ajax_data_from_request(data)
  if variable_name not in data:
    if required:
      raise AjaxProblem(
          'This request doesn\'t specify a {}'.format(variable_name))
    return None
  variable = data[variable_name]
  if required and variable in [None, '']:
    raise AjaxProblem('The {} is required'.format(variable_name))
  return variable


def get_ajax_data_from_request(request):
  return request.POST or request.PUT or request.DELETE


def do_simple_rest_request(
    request, klass, pk, create_function, update_function, delete_function):
  """ Do different things to an object depending on the request method and the
  pk. This always returns a JsonResponse object so it's totally up to you if
  you want to use the @ajax decorator on a view that uses this function. """
  obj = None
  if pk:
    obj = klass.objects.filter(pk=pk).first()
    if not obj:
      return problem_response('This {} doesn\'t exist'.format(
          klass._meta.model_name, 404))
  try:
    if request.method in ['POST', 'PUT']:
      data = get_ajax_data_from_request(request)
      if obj:
        return JsonResponse(update_function(obj, data))
      return JsonResponse(create_function(data))
    if request.method == 'DELETE':
      return JsonResponse(delete_function(obj))
  except AjaxProblem as ex:
    return ex.get_problem_response()
  return problem_response(
      'I\'m not sure what to do with a {} request'.format(request.method))
