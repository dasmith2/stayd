from smtplib import SMTPServerDisconnected
import os

from django.conf import settings
from django.core.mail import EmailMessage


class EmailExceptionTryLater(Exception):
  pass


class EmailSender(object):
  """ What if the very thing that's broken is sending email, and you want to
  experiment in the shell? Do this:

  from django.conf import settings
  settings.ALWAYS_ALLOW_SEND_MAIL = True

  Now when you log_error(...) for instance it'll actually send the email even
  though you're in the shell. """

  def send_mail(
      self, subject, email_message, from_email, to_emails,
      reply_to=None, ok_to_do_it_in_dev=False):
    if isinstance(to_emails, str):
      to_emails = [to_emails]
    if (settings.DEBUG or settings.SHELL) and (
        not settings.ALWAYS_ALLOW_SEND_MAIL):
      print('')
      print(subject)
      print(email_message)
      print('')
    elif settings.PROD or settings.STAGE or ok_to_do_it_in_dev or (
        settings.ALWAYS_ALLOW_SEND_MAIL):
      # I want to do this in stage so I get error emails. For instance I wasn't
      # getting post submission steps error emails.
      msg = EmailMessage(
          subject, email_message, from_email, to_emails,
          headers={'Reply-To': reply_to or from_email})
      try:
        return msg.send(fail_silently=False)
      except SMTPServerDisconnected:
        raise EmailExceptionTryLater()
    elif settings.TEST:
      pass
    else:
      raise Exception('Some unexpected pathway is trying to email notify!')


def send_csv(
    to, file_name, from_email=settings.SERVER_EMAIL,
    subject='CSV file attachment', email_content=''):
  """
  import csv
  from util.email import send_csv
  with open('some.csv', 'w') as f:
    writer = csv.writer(f)
    writer.writerow(['hello', 'world'])
  send_csv('dave@hihoward.com', 'some.csv')
  """
  msg = EmailMessage(subject, email_content, from_email, [to])
  msg.attach_file(file_name)
  msg.send(fail_silently=False)
  os.remove(file_name)
