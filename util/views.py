from django.http import HttpResponse


def trigger_error(request):
  return HttpResponse({}['triggered on purpose'])
