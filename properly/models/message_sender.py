from errors.models import ErrorLogger
from front.models import Front
from util.email import EmailSender


EMAIL = 'email'
SMS = 'sms'


class MessageSender(object):
  def send(
      self, message, front=Front(), error_logger=ErrorLogger(),
      email_sender=EmailSender()):
    if message.kind == SMS:
      message.delivery_error = front.delivery_error(
          front.send_sms(message.to, message.content))
    elif message.kind == EMAIL:
      if not message.to:
        message.delivery_error = 'There\'s no email to send this to'
      else:
        email_sender.send_mail(
            message.subject, message.content, settings.SERVER_EMAIL,
            [message.to])
    else:
      raise Exception(message.kind)
