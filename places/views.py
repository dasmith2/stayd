from django.http import HttpResponse
from places.models import Host

def list_hosts(request):
  host_list = []
  for host in Host.objects.all():
    host_list.append('<li>{}</li>'.format(host.name))
  return HttpResponse(
      '<html><body>hosts tests do not pass<ul>{}</ul></body></html>'.format(
      '\n'.join(host_list)))
