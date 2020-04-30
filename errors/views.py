from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from errors.models import log_error, StaydError


@csrf_exempt
def js_error(request):
  post = request.POST
  message = (
      'This is a Javascript error caught by '
      'static/js/util.js\n\nuser: {}\n\n{} line {} column {}'
      '\nReferer {}\nStack {}').format(
          request.user, post.get('url', ''),
          post.get('line', ''), post.get('col', ''),
          request.META.get('HTTP_REFERER', ''), post.get('stack', ''))
  subject = post.get('msg', 'Javascript error received')
  log_error(subject, message, supress_stack_trace=True)
  return HttpResponse('ok')


def see_error(request, pk):
  error = StaydError.objects.get(pk=pk)
  parts = [
      error.title,
      error.message,
      error.error_message,
      error.stack_trace]
  return HttpResponse(
      '\n'.join(['<pre>{}</pre>'.format(part) for part in parts]))
