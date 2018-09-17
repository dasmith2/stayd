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


def get_custom_fields_from_missing(problem_guesty_id):
  for fields in json.loads(MISSING):
    if fields['_id'] == problem_guesty_id:
      return fields['customFields']


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
    problem_guesty_id = json.loads(problem.json)['reservation']['_id']
    print('Fixing raw pk {}, guesty_id {}'.format(
        problem.pk, problem_guesty_id))
    previous = find_previous_webhook(problem)
    if previous:
      old_custom_fields = get_custom_fields_from_webhook(previous)
    else:
      old_custom_fields = get_custom_fields_from_missing(problem_guesty_id)
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


MISSING = """
[{
      "_id" : "5b57c46101095d00491f4866",
      "customFields" : [{
          "_id" : "5b57c46101095d00491f487a",
          "value" : true,
          "fieldId" : "5afec8950c6ec3001f42e5b2"
        }, {
          "_id" : "5b57c46101095d00491f4878",
          "value" : true,
          "fieldId" : "5afec8950c6ec3001f42e5b4"
        }, {
          "_id" : "5b57c46101095d00491f487f",
          "value" : true,
          "fieldId" : "5afecb67da85ff001f3f10fb"
        }, {
          "_id" : "5b57c46101095d00491f487d",
          "value" : true,
          "fieldId" : "5afa2c379ebb42009e34f26e"
        }, {
          "_id" : "5b57c46101095d00491f4882",
          "value" : true,
          "fieldId" : "5afa2c379ebb42009e34f26b"
        }, {
          "_id" : "5b57c46101095d00491f4876",
          "value" : true,
          "fieldId" : "5afec8950c6ec3001f42e5b6"
        }, {
          "_id" : "5b57c46101095d00491f4884",
          "value" : true,
          "fieldId" : "5afa2c379ebb42009e34f269"
        }, {
          "_id" : "5b57c46101095d00491f4875",
          "value" : true,
          "fieldId" : "5afa2c379ebb42009e34f271"
        }, {
          "_id" : "5b57c46101095d00491f487e",
          "value" : true,
          "fieldId" : "5b0d6444d8365d002ad94cb7"
        }, {
          "_id" : "5b57c46101095d00491f487b",
          "value" : true,
          "fieldId" : "5afec8950c6ec3001f42e5b1"
        }, {
          "_id" : "5b57c46101095d00491f4880",
          "value" : true,
          "fieldId" : "5afa2c379ebb42009e34f26d"
        }, {
          "_id" : "5b57c46101095d00491f4877",
          "value" : true,
          "fieldId" : "5afec8950c6ec3001f42e5b5"
        }, {
          "_id" : "5b57c46101095d00491f4885",
          "value" : true,
          "fieldId" : "5b299253f2177301cca1269a"
        }, {
          "_id" : "5b57c46101095d00491f487c",
          "value" : true,
          "fieldId" : "5afa2c379ebb42009e34f26f"
        }, {
          "_id" : "5b57c46101095d00491f4881",
          "value" : true,
          "fieldId" : "5afa2c379ebb42009e34f26c"
        }, {
          "_id" : "5b57c46101095d00491f4883",
          "value" : true,
          "fieldId" : "5afa2c379ebb42009e34f26a"
        }, {
          "fieldId" : "5b06aa98542e7f002a428c9d",
          "value" : 15,
          "_id" : "5b57c6b7c7af0a018c5258e"
        }, {
          "fieldId" : "5af5fd0dc3c35f0025b2642d",
          "value" : "ksneddon@krsworkplacelaw.com.au",
          "_id" : "5b57e921c5f4e3006de151a"
        }, {
          "fieldId" : "5af5fd0dc3c35f0025b2642e",
          "value" : true,
          "_id" : "5b58758ee845860067ea0ca"
        }
      ]
    },{
      "_id" : "5b5dede362098f003f7395f0",
      "customFields" : [{
          "_id" : "5b5dede362098f003f739604",
          "value" : true,
          "fieldId" : "5afec8950c6ec3001f42e5b2"
        }, {
          "_id" : "5b5dede362098f003f739609",
          "value" : true,
          "fieldId" : "5afecb67da85ff001f3f10fb"
        }, {
          "_id" : "5b5dede362098f003f73960e",
          "value" : true,
          "fieldId" : "5afa2c379ebb42009e34f269"
        }, {
          "_id" : "5b5dede362098f003f739601",
          "value" : true,
          "fieldId" : "5afec8950c6ec3001f42e5b5"
        }, {
          "_id" : "5b5dede362098f003f739606",
          "value" : true,
          "fieldId" : "5afa2c379ebb42009e34f26f"
        }, {
          "_id" : "5b5dede362098f003f739600",
          "value" : true,
          "fieldId" : "5afec8950c6ec3001f42e5b6"
        }, {
          "_id" : "5b5dede362098f003f73960b",
          "value" : true,
          "fieldId" : "5afa2c379ebb42009e34f26c"
        }, {
          "_id" : "5b5dede362098f003f739605",
          "value" : true,
          "fieldId" : "5afec8950c6ec3001f42e5b1"
        }, {
          "_id" : "5b5dede362098f003f73960a",
          "value" : true,
          "fieldId" : "5afa2c379ebb42009e34f26d"
        }, {
          "_id" : "5b5dede362098f003f73960f",
          "value" : true,
          "fieldId" : "5b299253f2177301cca1269a"
        }, {
          "_id" : "5b5dede362098f003f7395ff",
          "value" : true,
          "fieldId" : "5afa2c379ebb42009e34f271"
        }, {
          "_id" : "5b5dede362098f003f739602",
          "value" : true,
          "fieldId" : "5afec8950c6ec3001f42e5b4"
        }, {
          "_id" : "5b5dede362098f003f739607",
          "value" : true,
          "fieldId" : "5afa2c379ebb42009e34f26e"
        }, {
          "_id" : "5b5dede362098f003f73960c",
          "value" : true,
          "fieldId" : "5afa2c379ebb42009e34f26b"
        }, {
          "_id" : "5b5dede362098f003f739608",
          "value" : true,
          "fieldId" : "5b0d6444d8365d002ad94cb7"
        }, {
          "_id" : "5b5dede362098f003f73960d",
          "value" : true,
          "fieldId" : "5afa2c379ebb42009e34f26a"
        }, {
          "fieldId" : "5b06aa98542e7f002a428c9d",
          "value" : -2,
          "_id" : "5b5df009c7b310003e5d78e"
        }, {
          "fieldId" : "5af5fd0dc3c35f0025b2642d",
          "value" : "mlahrsow@gmail.com",
          "_id" : "5b5df11aad29be006ee85b3"
        }, {
          "fieldId" : "5af5fd0dc3c35f0025b2642e",
          "value" : true,
          "_id" : "5b5df3435d10770044f45d3"
        }
      ]
    }, {
      "_id" : "5b5fbef02c70fd0055422821",
      "customFields" : [{
          "_id" : "5b5fbef02c70fd0055422833",
          "value" : true,
          "fieldId" : "5afa2c379ebb42009e34f26f"
        }, {
          "_id" : "5b5fbef02c70fd005542282f",
          "value" : true,
          "fieldId" : "5afec8950c6ec3001f42e5b4"
        }, {
          "_id" : "5b5fbef02c70fd0055422838",
          "value" : true,
          "fieldId" : "5afa2c379ebb42009e34f26c"
        }, {
          "_id" : "5b5fbef02c70fd0055422831",
          "value" : true,
          "fieldId" : "5afec8950c6ec3001f42e5b2"
        }, {
          "_id" : "5b5fbef02c70fd0055422836",
          "value" : true,
          "fieldId" : "5afecb67da85ff001f3f10fb"
        }, {
          "_id" : "5b5fbef02c70fd005542282d",
          "value" : true,
          "fieldId" : "5afec8950c6ec3001f42e5b6"
        }, {
          "_id" : "5b5fbef02c70fd005542283b",
          "value" : true,
          "fieldId" : "5afa2c379ebb42009e34f269"
        }, {
          "_id" : "5b5fbef02c70fd005542282c",
          "value" : true,
          "fieldId" : "5afa2c379ebb42009e34f271"
        }, {
          "_id" : "5b5fbef02c70fd0055422832",
          "value" : true,
          "fieldId" : "5afec8950c6ec3001f42e5b1"
        }, {
          "_id" : "5b5fbef02c70fd0055422834",
          "value" : true,
          "fieldId" : "5afa2c379ebb42009e34f26e"
        }, {
          "_id" : "5b5fbef02c70fd0055422837",
          "value" : true,
          "fieldId" : "5afa2c379ebb42009e34f26d"
        }, {
          "_id" : "5b5fbef02c70fd0055422839",
          "value" : true,
          "fieldId" : "5afa2c379ebb42009e34f26b"
        }, {
          "_id" : "5b5fbef02c70fd005542283c",
          "value" : true,
          "fieldId" : "5b299253f2177301cca1269a"
        }, {
          "_id" : "5b5fbef02c70fd005542282e",
          "value" : true,
          "fieldId" : "5afec8950c6ec3001f42e5b5"
        }, {
          "_id" : "5b5fbef02c70fd0055422835",
          "value" : true,
          "fieldId" : "5b0d6444d8365d002ad94cb7"
        }, {
          "_id" : "5b5fbef02c70fd005542283a",
          "value" : true,
          "fieldId" : "5afa2c379ebb42009e34f26a"
        }, {
          "fieldId" : "5b06aa98542e7f002a428c9d",
          "value" : 5,
          "_id" : "5b5fbf9bd84194004448a76"
        }, {
          "fieldId" : "5af5fd0dc3c35f0025b2642d",
          "value" : "inkpubs@gmail.com",
          "_id" : "5b5fc18ad2062c006c418ec"
        }, {
          "fieldId" : "5af5fd0dc3c35f0025b2642e",
          "value" : true,
          "_id" : "5b5fc6de99dc02006e86d4c"
        }
      ]
    },{
      "_id" : "5b603791972ad1004a1fc50a",
      "customFields" : [{
          "_id" : "5b603791972ad1004a1fc51c",
          "value" : true,
          "fieldId" : "5afec8950c6ec3001f42e5b4"
        }, {
          "_id" : "5b603791972ad1004a1fc521",
          "value" : true,
          "fieldId" : "5afa2c379ebb42009e34f26e"
        }, {
          "_id" : "5b603791972ad1004a1fc519",
          "value" : true,
          "fieldId" : "5afa2c379ebb42009e34f271"
        }, {
          "_id" : "5b603791972ad1004a1fc526",
          "value" : true,
          "fieldId" : "5afa2c379ebb42009e34f26b"
        }, {
          "_id" : "5b603791972ad1004a1fc51b",
          "value" : true,
          "fieldId" : "5afec8950c6ec3001f42e5b5"
        }, {
          "_id" : "5b603791972ad1004a1fc520",
          "value" : true,
          "fieldId" : "5afa2c379ebb42009e34f26f"
        }, {
          "_id" : "5b603791972ad1004a1fc525",
          "value" : true,
          "fieldId" : "5afa2c379ebb42009e34f26c"
        }, {
          "_id" : "5b603791972ad1004a1fc51e",
          "value" : true,
          "fieldId" : "5afec8950c6ec3001f42e5b2"
        }, {
          "_id" : "5b603791972ad1004a1fc523",
          "value" : true,
          "fieldId" : "5afecb67da85ff001f3f10fb"
        }, {
          "_id" : "5b603791972ad1004a1fc528",
          "value" : true,
          "fieldId" : "5afa2c379ebb42009e34f269"
        }, {
          "_id" : "5b603791972ad1004a1fc51a",
          "value" : true,
          "fieldId" : "5afec8950c6ec3001f42e5b6"
        }, {
          "_id" : "5b603791972ad1004a1fc51f",
          "value" : true,
          "fieldId" : "5afec8950c6ec3001f42e5b1"
        }, {
          "_id" : "5b603791972ad1004a1fc524",
          "value" : true,
          "fieldId" : "5afa2c379ebb42009e34f26d"
        }, {
          "_id" : "5b603791972ad1004a1fc529",
          "value" : true,
          "fieldId" : "5b299253f2177301cca1269a"
        }, {
          "_id" : "5b603791972ad1004a1fc522",
          "value" : true,
          "fieldId" : "5b0d6444d8365d002ad94cb7"
        }, {
          "_id" : "5b603791972ad1004a1fc527",
          "value" : true,
          "fieldId" : "5afa2c379ebb42009e34f26a"
        }, {
          "fieldId" : "5b06aa98542e7f002a428c9d",
          "value" : -5,
          "_id" : "5b603b8ac04acb003ad3d9a"
        }, {
          "fieldId" : "5af5fd0dc3c35f0025b2642d",
          "value" : "ethiriez@gmail.com",
          "_id" : "5b603db4050568006895938"
        }, {
          "fieldId" : "5af5fd0dc3c35f0025b2642e",
          "value" : true,
          "_id" : "5b60447d3f877a0067f8fc9"
        }
      ]
    }
    ]
"""
