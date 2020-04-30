from django.conf import settings
from django.core.mail import send_mail
from django.http import HttpResponse
from django.shortcuts import redirect, reverse, render


def message(title, text, status):
  """ Return a page with a message on it. """
  return render(None, 'bare_bones_message.html', status=status, context={
      'title': title, 'message': text})


def trigger_error(request):
  """ /trigger_error/ """
  return HttpResponse({}['triggered on purpose'])


def email_admins(request):
  emails = [a[1] for a in settings.ADMINS]
  send_mail(
      'Test sending email to each admin', 'Testing', 'heroku@stayd.com',
      emails, fail_silently=False)
  to = '<br>'.join(emails)
  return HttpResponse('Sent emails to:<br>{}'.format(to))


def homepage(request):
  return redirect(homepage_by_host(request.META['HTTP_HOST']))


def homepage_by_host(host):
  if host.find('owners') >= 0:
    return reverse('dashboard')
  elif host.find('guests') >= 0 or host.find('verifyid') >= 0:
    return reverse('verify_id')
  elif host.find('admin') >= 0 or host.find('vh') >= 0:
    return reverse('submissions')
  elif host.find('clean') >= 0:
    return reverse('clean_co_cleanings')
  elif host.find('work') >= 0:
    return reverse('my_tickets')
  elif host.find('walls') >= 0 or host.find('art') >= 0:
    return reverse('walls')
  elif host.find('guestlist') >= 0:
    return reverse('door_person')
  return '/admin'


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
