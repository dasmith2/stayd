from guest_messages.models.email import Email
from guest_messages.models.sms import SMS
from util.table import Table


def get_message_list_table(reservation):
  table = Table([
      'Type', 'Reason', 'Switched on?', 'When should', 'When did', 'Sent to',
      'Why didn\'t?', 'Contents', 'SMS verified/email opened',
      'Delivery error'])
  smss = SMS.objects.get_for_reservation(reservation)
  emails = Email.objects.get_for_reservation(reservation)
  both = reversed(sorted(
      list(smss) + list(emails), key=lambda x: x.when_should))
  for message in both:
    reason = message.guesty_custom_field_name()
    switched_on = message.green_light
    if isinstance(message, SMS):
      delivered = message.delivery_check_on
    else:
      delivered = message.opened
    table.create_row([
        message.get_pretty_type(), reason, switched_on, message.when_should,
        message.when_did, message.sent_to, message.why_did_not_send,
        message.describe_contents(), delivered, message.delivery_error])
  return table
