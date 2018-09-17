"""
One time, we did this integration with everydoor and they tried to write custom
fields to a bunch of reservations without realizing that by only writing their
fields, they accidentally erased all of ours. So this goes through the raw
events in a specific window when the problem happened, found the webhooks
with those fields, then found the previous webhook, then merged the custom
fields of the previous webhook with the current custom fields for that
reservation, then wrote the merged list back to guesty.
"""
import json

from commands.stayd_command import StaydCommand

from guests.models import Guest
from guesty.api import get_one
from guesty.api_getter import GuestyAPIGetter
from guesty.custom_fields import CustomFields
from guesty.models import RawEvent
from reservations.models import Reservation
from util.timezone import parse_dt


def find_problem_webhooks():
  for raw in RawEvent.objects.filter(
      created_at__gt=parse_dt('2018-09-13 18:25'),
      created_at__lt=parse_dt('2018-09-13 18:59')):
    if json.loads(raw.json)['reservation']['status'] == 'confirmed':
      for field in get_custom_fields_from_webhook(raw):
        if field['fieldId'] == '5b9ad33f791c2e00a93bee8d':
          yield raw


def problem_id_set():
  problems = find_problem_webhooks()
  return set([json.loads(p.json)['reservation']['_id'] for p in problems])


def print_resolution():
  seen_already = set()
  for problem in find_problem_webhooks():
    res = json.loads(problem.json)['reservation']
    guesty_id = res['_id']
    if guesty_id not in seen_already:
      seen_already.add(guesty_id)
      guest_name = get_one(Guest, res['guestId'])['fullName']
      print('{}\nhttps://app.guesty.com/reservations/{}/guests\n'.format(
          guest_name, guesty_id))


def find_previous_webhook(webhook):
  return RawEvent.objects.filter(
      reservation=webhook.reservation,
      pk__lt=webhook.pk).order_by('-pk').first()


def get_custom_fields_from_webhook(webhook):
  return json.loads(webhook.json)['reservation']['customFields']


def get_custom_fields_for_res(reservation):
  custom_fields = CustomFields(
      Reservation, reservation.guestyreservation.guesty_id)
  custom_fields.download_custom_fields()
  return custom_fields


def put_old_fields_back_in(new_custom_fields, old):
  for old_field in old:
    old_field_id = old_field['fieldId']
    found = False
    for new_field in new_custom_fields.custom_fields:
      new_field_id = new_field['fieldId']
      found = found or old_field_id == new_field_id
    if not found:
      new_custom_fields.set(old_field_id, old_field['value'])


def fix_all():
  for problem in find_problem_webhooks():
    print('Fixing raw pk {}, guesty_id {}'.format(
        problem.pk, json.loads(problem.json)['reservation']['_id']))
    previous = find_previous_webhook(problem)
    if previous:
      old_custom_fields = get_custom_fields_from_webhook(previous)
      reservation = problem.reservation
      new_custom_fields = get_custom_fields_for_res(reservation)
      put_old_fields_back_in(new_custom_fields, old_custom_fields)
      new_custom_fields.send_changes(GuestyAPIGetter())


class Command(StaydCommand):
  def run(self, verbose):
    fix_all()

  help = (
      'Find those everydoor webhooks that wiped out our data and '
      'restore the custom fields that existed before.')

  def name(self):
    return 'fix_everydoor'
