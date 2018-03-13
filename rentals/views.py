from django.http import HttpResponse


def list_hosts(request):
  return HttpResponse('Hello world!')
