from django.conf import settings
from django.core.mail import send_mail


class EmailSender(object):
  def send_mail(
      self, subject, email_message, from_email, to_emails,
      ok_to_do_it_in_dev=False):
    if settings.PROD or ok_to_do_it_in_dev:
      return send_mail(
          subject, email_message, from_email, to_emails, fail_silently=False)
    elif settings.TEST or settings.STAGE:
      pass
    elif settings.DEBUG:
      print('')
      print(subject)
      print(email_message)
      print('')
    else:
      raise Exception('Some unexpected pathway is trying to email notify!')
