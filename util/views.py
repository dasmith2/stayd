from django.conf import settings
from django.core.mail import send_mail
from django.http import HttpResponse


def trigger_error(request):
  return HttpResponse({}['triggered on purpose'])


def email_admins(request):
  send_mail(
      'Test sending email to each admin', 'Testing', 'heroku@staydd.com',
      settings.ADMINS, fail_silently=False)
  to = '<br>'.join(settings.ADMINS)
  return HttpResponse('Sent emails to:<br>{}'.format(to))
