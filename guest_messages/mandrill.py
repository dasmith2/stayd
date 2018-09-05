from django.conf import settings

from guest_messages.mandrill_examples import SEND_RESULT
from mandrill import Mandrill


_mandrill = Mandrill(settings.MANDRILL_API_KEY)


class Emailer(object):
  def __init__(self, mandrill_api_messages=None):
    self.mandrill_api_messages = mandrill_api_messages or _mandrill.messages

  def send_email(
      self, subject, to, template_params, template_name,
      dont_do_it_in_dev=True):
    """ `to` is just a single email address. """
    mandrill_params = []
    for key, value in template_params.items():
      mandrill_params.append({'name': key, 'content': value})
    message = {
        'from_email': settings.GUEST_EMAILS_FROM,
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
    if settings.TEST:
      return SEND_RESULT
    elif settings.DEBUG and dont_do_it_in_dev:
      print()
      print(to)
      print(subject)
      print()
      return SEND_RESULT
    return self.mandrill_api_messages.send_template(
        template_name, template_content, message, async=False)
