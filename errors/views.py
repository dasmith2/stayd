from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from errors.models import log_error


@csrf_exempt
def js_error(request):
  post = request.POST
  log_error(
      'Javascript {}'.format(post['msg']),
      '{} line {} column {}'.format(post['url'], post['line'], post['col']))
  return HttpResponse('ok')
