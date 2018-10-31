from django.conf import settings
from django.core.mail import send_mail


class EmailSender(object):
  def send_mail(
      self, subject, email_message, from_email, to_emails,
      ok_to_do_it_in_dev=False):
    if settings.DEBUG or settings.SHELL:
      print('')
      print(subject)
      print(email_message)
      print('')
    elif settings.PROD or settings.STAGE or ok_to_do_it_in_dev:
      # I want to do this in stage so I get error emails. For instance I wasn't
      # getting post submission steps error emails.
      return send_mail(
          subject, email_message, from_email, to_emails, fail_silently=False)
    elif settings.TEST:
      pass
    else:
      raise Exception('Some unexpected pathway is trying to email notify!')
