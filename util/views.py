from django.conf import settings
from django.core.mail import send_mail
from django.http import HttpResponse
from django.shortcuts import redirect, reverse, render


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
  if host.find('owners') >= 0:
    return redirect(reverse('dashboard'))
  elif host.find('guests') >= 0:
    return redirect(reverse('verify_id'))
  elif host.find('admin') >= 0:
    return redirect(reverse('submissions'))
  return redirect('/admin')


def error_404_view(request, exception):
  context = {'title': '404', 'message': 'Not found'}
  return render(request, 'blue_message.html', context, status=404)


def error_500_view(request):
  context = {
      'title': 'Well that\'s embarrassing',
      'message': (
          'You just hit an error and it\'s all our fault. Software, you '
          'know? Hard to get it right. Anyway I notified the software '
          'developers and they\'ll get right on it.')}
  return render(request, 'blue_message.html', context, status=500)
