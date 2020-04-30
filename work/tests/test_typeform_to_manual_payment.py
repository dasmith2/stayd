import copy
import json
from unittest.mock import Mock, call

from django.conf import settings
from djmoney.money import Money

from rentals.tests import get_test_owner
from work.models.message import (
    Message, MessageSender,
    CANT_FIND_RECEIPT_BUILDING_BY_NICKNAME, CANT_FIND_RECEIPT_WORKER_BY_PHONE,
    NEW_RECEIPT)
from work.models.payment import ManualPayment
from work.tests.test_work import get_test_independent_worker
from work.tests.test_work_co import get_test_work_co
from work.tests.test_work_co_worker import get_test_work_co_worker
from rentals.tests import get_test_building
from typeform.api_examples import SUBMIT_RECEIPT_EXAMPLE
from typeform.models import RawEvent, Response
from util.tests import TestCase


class TypeformTests(TestCase):
  def setUp(self):
    super().setUp()
    self.building = get_test_building(nickname='243 Montgomery St')

  def test_submit_receipt(self):
    dave = get_test_independent_worker(phone='917-608-4623')
    message_sender = Mock(spec=MessageSender)
    RawEvent.objects.create(json=json.dumps(SUBMIT_RECEIPT_EXAMPLE)).handle(
        message_sender=message_sender)

    self.assertEqual(1, Response.objects.count())
    self.assertEqual(1, ManualPayment.objects.count())
    pay = ManualPayment.objects.first()
    self.assertEqual(dave, pay.worker.get_child_class_instance())
    self.assertEqual(self.building, pay.building)
    receipt_photo_url = (
        'https://api.typeform.com/responses/files/'
        '97bfa65f1b0c43a8f27ba8ef27d2ad48f6d097919cfc89bdd73d12e6d8d5d199/'
        '15537160199078310759240903748020.jpg')
    self.assertEqual(receipt_photo_url, pay.receipt_photo_url)
    self.assertEqual('I bought tests so I could test the test.', pay.message)
    self.assertEqual(Money('12.34', 'USD'), pay.amount)
    self.assertTrue(bool(pay.on_hold_reason))
    self.assertEqual(
        'Created automatically. Please verify!', pay.on_hold_reason)

    message = Message.objects.get(
        reason=NEW_RECEIPT, to=settings.ALERT_NEW_RECEIPT)
    self.assertEqual([call(message)], message_sender.send.call_args_list)

  def test_independent_worker_email(self):
    dave = get_test_independent_worker(email='dave@independent.worker')
    response_data = copy.deepcopy(SUBMIT_RECEIPT_EXAMPLE)
    response_data['form_response']['answers'][0]['text'] = (
        'dave@independent.worker')

    message_sender = Mock(spec=MessageSender)
    RawEvent.objects.create(json=json.dumps(response_data)).handle(
        message_sender=message_sender)
    self.assertEqual(
        dave, ManualPayment.objects.first().worker.get_child_class_instance())

  def test_bad_number(self):
    message_sender = Mock(spec=MessageSender)
    RawEvent.objects.create(json=json.dumps(SUBMIT_RECEIPT_EXAMPLE)).handle(
        message_sender=message_sender)

    self.assertEqual(1, Response.objects.count())
    self.assertEqual(1, ManualPayment.objects.count())
    pay = ManualPayment.objects.first()
    self.assertIsNone(pay.worker)
    message = Message.objects.get(reason=CANT_FIND_RECEIPT_WORKER_BY_PHONE)
    self.assertEqual([call(message)], message_sender.send.call_args_list)


class BadBuildingTests(TestCase):
  def test_bad_building(self):
    get_test_independent_worker(phone='917-608-4623')

    message_sender = Mock(spec=MessageSender)
    RawEvent.objects.create(json=json.dumps(SUBMIT_RECEIPT_EXAMPLE)).handle(
        message_sender=message_sender)

    message = Message.objects.get(
        reason=CANT_FIND_RECEIPT_BUILDING_BY_NICKNAME)
    self.assertEqual([call(message)], message_sender.send.call_args_list)


class WorkCoTests(TestCase):
  def setUp(self):
    super().setUp()
    self.building = get_test_building(nickname='243 Montgomery St')
    owner = get_test_owner(email='work@co.owner')
    self.work_co = get_test_work_co(owner=owner, alerts_email='alerts@work.co')
    get_test_work_co_worker(work_co=self.work_co, email='work@co.worker')

  def test_work_co_owner_email(self):
    response_data = copy.deepcopy(SUBMIT_RECEIPT_EXAMPLE)
    response_data['form_response']['answers'][0]['text'] = 'work@co.owner'

    message_sender = Mock(spec=MessageSender)
    RawEvent.objects.create(json=json.dumps(response_data)).handle(
        message_sender=message_sender)
    self.assertEqual(self.work_co, ManualPayment.objects.first().work_co)

  def test_work_co_alerts_email(self):
    response_data = copy.deepcopy(SUBMIT_RECEIPT_EXAMPLE)
    response_data['form_response']['answers'][0]['text'] = 'alerts@work.co'

    message_sender = Mock(spec=MessageSender)
    RawEvent.objects.create(json=json.dumps(response_data)).handle(
        message_sender=message_sender)
    self.assertEqual(self.work_co, ManualPayment.objects.first().work_co)

  def test_work_co_worker_email(self):
    response_data = copy.deepcopy(SUBMIT_RECEIPT_EXAMPLE)
    response_data['form_response']['answers'][0]['text'] = 'work@co.worker'

    message_sender = Mock(spec=MessageSender)
    RawEvent.objects.create(json=json.dumps(response_data)).handle(
        message_sender=message_sender)
    self.assertEqual(self.work_co, ManualPayment.objects.first().work_co)
