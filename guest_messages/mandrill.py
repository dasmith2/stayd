from django.conf import settings

from mandrill import Mandrill


_mandrill = Mandrill(settings.MANDRILL_API_KEY)


def send_email(
    subject, to, template_params, template_name, mandrill_api=_mandrill):
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
  return mandrill_api.messages.send_template(
      template_name, template_content, message, async=False)
