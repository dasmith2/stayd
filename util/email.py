from django.conf import settings
from django.core.mail import send_mail


class EmailSender(object):
  def send_mail(
      self, subject, email_message, from_email, to_emails):
    if settings.DEBUG:
      print('')
      print(subject)
      print(email_message)
      print('')
    else:
      send_mail(subject, email_message, from_email, to_emails)
