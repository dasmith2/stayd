"""
Tests for pays.
"""
from datetime import datetime, date
import pytz

from django.conf import settings
from django.utils.six import BytesIO
from djmoney.money import Money
from django.test import TestCase
from django.utils.timezone import make_aware
import moneyed
from rest_framework.renderers import JSONRenderer
from rest_framework.parsers import JSONParser

from pays.models import Payable, PaypalPayout, PaypalPayin
from pays.serializers import PaypalPayinSerializer
from pays.paypal_api import MockPaypalApi


def get_test_paypal_payin(create, **kwargs):
  paypal_payin = PaypalPayin(
      amount=kwargs.get('amount', Money(65, moneyed.AUD)),
      when=kwargs.get('when', datetime(2018, 2, 14)),
      transaction_id=kwargs.get('transaction_id', 'sie875chbs5'),
      to_email=kwargs.get('to_email', 'pay_me_my_money@gmail.com'))
  if create:
    paypal_payin.save()
  return paypal_payin


class PayinSerializationTests(TestCase):
  def test_serializing_loaded_object(self):
    # When the API returns one that's been saved to the database,
    # it serializes it. Make sure that works.
    PaypalPayinSerializer(get_test_paypal_payin(
        True, when=make_aware(datetime(2018, 2, 14)))).data

  def test_serializing_manual_object_and_saving(self):
    # Pretend we're in a scraper and want to put together a listing
    # to save.
    p = get_test_paypal_payin(
        False,
        transaction_id='ibelieveinafingcalledlove',
        amount=Money(66, moneyed.BAM))

    # Make sure it doesn't exist yet.
    self.assertEqual(0, len(PaypalPayin.objects.filter(
        transaction_id='ibelieveinafingcalledlove')))

    # Serialize, deserialize, and save twice. The second time around, change
    # the amount.
    for i in range(2):
      if i == 1:
        p.amount = Money(67, moneyed.CAD)
      serializer = PaypalPayinSerializer(p)
      content = JSONRenderer().render(serializer.data)
      stream = BytesIO(content)
      data = JSONParser().parse(stream)
      deserializer = PaypalPayinSerializer(data=data)
      self.assertTrue(deserializer.is_valid())
      deserializer.create(deserializer.validated_data)

    # Make sure we didn't make extra objects.
    payins = PaypalPayin.objects.filter(
        transaction_id='ibelieveinafingcalledlove')
    self.assertEqual(1, len(payins))

    # Make sure the saved versions are equal to what we expected.
    loaded_p = payins[0]

    self.assertEqual(p.amount, loaded_p.amount)
    # Just go ahead and let Django assign the default time zone to `when`.
    expected = pytz.timezone(settings.TIME_ZONE).localize(p.when)
    self.assertEqual(expected, loaded_p.when)
    self.assertEqual(p.transaction_id, loaded_p.transaction_id)
    self.assertEqual(p.to_email, loaded_p.to_email)


class PaypalPayoutTests(TestCase):
  def get_a_test_payout(self):
    payable = Payable.objects.create(email='does_not_exist_t81nx9j3@gmail.com')
    payout = PaypalPayout.init_new_payout(
        who_to_pay=payable,
        amount=Money(1, 'USD'),
        email_subject='Test email subject',
        note='Test note',
        when_should=date.today())
    payout.paypal_api = MockPaypalApi()
    return payout

  def test_weird_response(self):
    payout = self.get_a_test_payout()
    payout.paypal_api.custom_response = {'hello': 'world!'}
    payout.send()
    self.assertEqual('API_ERROR', payout.error_name)
    self.assertEqual("{'hello': 'world!'}", payout.error_message)

  def test_insufficient_funds(self):
    payout = self.get_a_test_payout()
    payout.paypal_api.insufficient_funds = True
    payout.send()
    self.assertEqual('INSUFFICIENT_FUNDS', payout.error_name)

  def test_send(self):
    payout = self.get_a_test_payout()

    payout.send()

    self.assertTrue(payout.payout_batch_id)
    self.assertEqual(0, payout.sender_batch_id.index('{}-'.format(payout.pk)))
    self.assertEqual(0, payout.sender_item_id.index('{}-'.format(payout.pk)))
    self.assertEqual(
        payout.who_to_pay.email, 'does_not_exist_t81nx9j3@gmail.com')
    self.assertEqual(payout.email_subject, 'Test email subject')
    self.assertEqual(payout.note, 'Test note')
    self.assertEqual(payout.batch_status, 'PENDING')

  def test_check_status(self):
    payout = self.get_a_test_payout()
    self.assertIsNone(payout.when_did)

    # This runs against a mocked Paypal API.
    payout.check_status()
    payout = PaypalPayout.objects.get(pk=payout.pk)

    self.assertEqual(payout.batch_status, 'SUCCESS')
    self.assertEqual(payout.paypal_fee, Money(.25, 'USD'))

    self.assertEqual(payout.transaction_status, 'UNCLAIMED')
    self.assertTrue(payout.transaction_id)
    self.assertIsNotNone(payout.when_did)

    self.assertTrue(payout.payout_item_id)
    self.assertEqual(payout.error_name, 'RECEIVER_UNREGISTERED')
    self.assertEqual(payout.error_message, "This receiver is not registered.")
