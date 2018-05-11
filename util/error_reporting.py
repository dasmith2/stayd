from django.conf import settings
from django.core.mail import send_mail


def resolve_me(subject, content):
  """ Call this when there's a well understood problem that somebody
  can solve, and in the meantime we can keep processing.
  settings.THIS_SERVERS_BASE_URL """
  if settings.DEBUG:
    print()
    print(subject)
    print(content)
    print()
  else:
    send_mail(
        subject, content, 'heroku@stayd.com', ['heroku-errors@stayd.com'],
        fail_silently=False)
