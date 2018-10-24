from django.core.mail import send_mail

from util.background import background


@background
def send_email(subject):
  send_mail(
      subject, str(sys.argv), 'heroku@stayd.com', ['dave@stayd.com'])
