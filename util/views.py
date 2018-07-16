from django.conf import settings
from django.core.mail import send_mail
from django.http import HttpResponse
from django.shortcuts import redirect, reverse


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
  host = request.META['HTTP_HOST']
  if host.find('guests') >= 0:
    return redirect(reverse('verify_id'))
  elif host.find('admin') >= 0:
    return redirect(reverse('submissions'))
  return HttpResponse(
      'Host {}, host.find admin {}'.format(host, host.find('admin')))
