from django.core.management.base import BaseCommand
from django.core.mail import send_mail


class Command(BaseCommand):
  help = 'Send a test email.'

  def handle(self, *args, **options):
    send_mail(
        'Hello world!', 'This is your test email.', 'heroku@stayd.com',
        ['heroku@stayd.com'], fail_silently=False)
