from django.conf import settings

from front.models import Front
from util.email import EmailSender


EMAIL = 'email'
SMS = 'sms'


class MessageSender(object):
  def __init__(self, front=Front(), email_sender=EmailSender()):
    self.front = front
    self.email_sender = email_sender

  def send(self, message):
    if message.kind == SMS:
      if message.subject:
        raise Exception(
            'With SMS, I expect an empty subject. This has {}'.format(
                message.subject))
      message.delivery_error = self.front.delivery_error(
          self.front.send_sms(message.to, message.content))
    elif message.kind == EMAIL:
      if not message.to:
        message.delivery_error = 'There\'s no email to send this to'
      else:
        self.email_sender.send_mail(
            message.subject, message.content, settings.SERVER_EMAIL,
            [message.to])
    else:
      raise Exception(message.kind)
