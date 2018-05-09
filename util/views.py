from django.conf import settings
from django.core.mail import send_mail
from django.http import HttpResponse
from django.shortcuts import redirect


def trigger_error(request):
  return HttpResponse({}['triggered on purpose'])


def email_admins(request):
  emails = [a[1] for a in settings.ADMINS]
  send_mail(
      'Test sending email to each admin', 'Testing', 'heroku@stayd.com',
      emails, fail_silently=False)
  to = '<br>'.join(emails)
  return HttpResponse('Sent emails to:<br>{}'.format(to))


def homepage(request):
  return redirect('/admin')
