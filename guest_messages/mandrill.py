from django.conf import settings

from guest_messages.mandrill_examples import SEND_RESULT
from mandrill import Mandrill


_mandrill = Mandrill(settings.MANDRILL_API_KEY)


class Emailer(object):
  def __init__(self, mandrill_api_messages=None):
    self.mandrill_api_messages = mandrill_api_messages or _mandrill.messages

  def send_email(
      self, subject, to, template_params, template_name,
      ok_to_do_it_in_dev=False):
    """ `to` is just a single email address.

    It's ok_to_do_it_in_dev when mandrill_api_messages is mocked, you're
    testing manually in a shell, or you're using the workflow where you send a
    test email to yourself on the email templates admin page. """

    mandrill_params = []
    for key, value in template_params.items():
      mandrill_params.append({'name': key, 'content': value})
    message = {
        'from_email': settings.GUEST_EMAILS_FROM,
        'from_name': settings.GUEST_EMAILS_FROM_NAME,
        'global_merge_vars': mandrill_params,
        # This is a whole thing.
        # https://mandrill.zendesk.com/hc/en-us/articles/205582437-CSS-Inlining
        'inline_css': True,
        'to': [{'email': to}],
        'headers': {'Reply-To': settings.GUEST_EMAILS_REPLY_TO},
        'track_opens': True,
        'track_clicks': True,
        'subject': subject}
    template_content = []  # Populates content blocks.
    if (settings.PROD and settings.BACKGROUND) or ok_to_do_it_in_dev:
      return self.mandrill_api_messages.send_template(
          template_name, template_content, message, async=False)
    elif settings.TEST:
      return SEND_RESULT
    elif settings.DEBUG:
      print()
      print(to)
      print(subject)
      print()
      return SEND_RESULT
    elif settings.STAGE:
      pass
    else:
      raise Exception('Some unexpected pathway is trying to send Emails!')
