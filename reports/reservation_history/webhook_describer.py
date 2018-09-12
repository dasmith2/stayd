import json

from django.urls import reverse

from guest_messages.models.models_base import (
    GUESTY_MESSAGE_TOGGLE_CUSTOM_FIELDS)
from guesty.custom_fields import CustomFields
from guesty.models import RawEvent
from reservations.models import Reservation


class WebhookDiff(object):
  def __init__(self, raw_event, new_things, removed_things):
    self.url = reverse('see_raw_event_json', kwargs={'pk': raw_event.pk})
    self.event_name = raw_event.event_name
    self.created_at = raw_event.created_at
    self.handled_at = raw_event.handled_at
    self.new_things = new_things
    self.removed_things = removed_things


class WebhookDescriber(object):
  def get_diffs(self, reservation):
    diffs = []
    webhooks = RawEvent.objects.filter(
        reservation=reservation).order_by('created_at')
    last_things = set()
    for webhook in webhooks:
      r_long = json.loads(webhook.json)['reservation']
      these_things = self._get_things(r_long)
      diffs.append(WebhookDiff(
          webhook, sorted(these_things - last_things),
          sorted(last_things - these_things)))
      last_things = these_things
    return list(reversed(diffs))

  def _get_things(self, r_long):
    guesty_id = r_long['_id']
    custom_fields_dict = r_long['customFields']
    custom_fields = CustomFields(Reservation, guesty_id, custom_fields_dict)
    things = set([
        'SMS enabled - {}'.format(custom_fields.messages_enabled()),
        'custom field: id verified - {}'.format(custom_fields.id_verified()),
        'custom field: email provided - {}'.format(
            custom_fields.email_provided()),
        'custom field: phone provided - {}'.format(
            custom_fields.phone_provided()),
        'custom field: paid in full - {}'.format(custom_fields.paid_in_full()),
        'custom field: credit card authorization_valid - {}'.format(
            custom_fields.credit_card_authorization_valid())])
    for field in [
        'checkIn', 'checkOut', 'plannedArrival', 'confirmationCode',
            'createdAt', 'importedAt', 'source', 'status']:
      things.add('reservation: {} - {}'.format(field, r_long.get(field, '')))
    money = r_long['money']
    for field in [
        'balanceDue', 'fareAccommodation', 'fareCleaning', 'hostPayout',
            'hostServiceFee']:
      things.add('money: {} - {}'.format(field, money.get(field, '')))
    for payment in money.get('payments', []):
      things.add('money payment: {} {}. isAuthorizationHold - {}'.format(
          payment.get('amount', ''), payment.get('status', ''),
          payment.get('isAuthorizationHold', '')))
    for guesty_field_id, description in GUESTY_MESSAGE_TOGGLE_CUSTOM_FIELDS:
      things.add('SMS enabled: {} - {}'.format(
          description, custom_fields.get(guesty_field_id, 'Default (True)')))
    return things
