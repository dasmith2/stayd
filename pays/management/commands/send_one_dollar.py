from django.core.management.base import BaseCommand, CommandError

from pays.models import PayableEmail

class Command(BaseCommand):
  help = 'Send US$1 to the specified email using Paypal'

  def add_arguments(self, parser):
    parser.add_argument('email')

  def handle(self, *args, **options):
    email = options['email']
    PayableEmail.send_test_dollar_via_paypal_to_email(options['email'])
    self.stdout.write(self.style.SUCCESS('Sent US$1 to {}.'.format(email)))
