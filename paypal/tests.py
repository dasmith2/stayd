from unittest.mock import Mock, call

from django.conf import settings
from django.utils.dateparse import parse_datetime
from djmoney.money import Money

from errors.models import ErrorLogger, Notifier
from paypal.api import API
from paypal.api_examples import (
    SUCCESSFULL_SEND, FAILED_SEND, SUCCESS_STATUS, ERROR_STATUS)
from paypal.models import Payout, check_status_background, SUCCESS
from util.tests import TestCase
from util.timezone import str_to_tz_dt


def get_successful_payout(**kwargs):
  kwargs['batch_status'] = SUCCESS
  kwargs['transaction_status'] = ''
  kwargs['when_did'] = kwargs.get('when_did', str_to_tz_dt('2018-10-15 12:00'))
  return get_test_payout(**kwargs)


def get_test_payout(**kwargs):
  return Payout.objects.create(
      pay_email=kwargs.get('pay_email', 'pay_me@email.com'),
      amount=kwargs.get('amount', Money('10.0', 'USD')),
      email_subject=kwargs.get('email_subject', 'Email subject here'),
      note=kwargs.get('note', 'Note here'),
      when_should=kwargs.get('when_should', str_to_tz_dt('2018-10-15 12:00')),
      when_did=kwargs.get('when_did', None),
      paypal_fee=kwargs.get('paypal_fee', Money('0.25', 'USD')),
      payout_batch_id=kwargs.get('payout_batch_id', 'parootbarchoodee'),
      sender_batch_id=kwargs.get('sender_batch_id', 'sarndeerboocheedee'),
      payout_item_id=kwargs.get('payout_item_id', 'paruteetomeyedoof'),
      transaction_id=kwargs.get('transaction_id', 'flarginblarpin'),
      transaction_status=kwargs.get('transaction_status', 'whuptydoodahday'),
      batch_status=kwargs.get('batch_status', 'blubber'),
      error_name=kwargs.get('error_name', ''),
      error_message=kwargs.get('error_message', ''))


class PayoutTests(TestCase):
  def test_get_send_data(self):
    payout = Payout.objects.init_new_payout(
        pay_email='doov@dave.deeve', amount=Money('12.34', 'USD'),
        email_subject='Hey! Subject!', note='Uh... note.',
        when_should=str_to_tz_dt('2018-10-15 12:00'))
    self.assertTrue(bool(payout.sender_batch_id))
    expected = {
        'sender_batch_header': {
            'sender_batch_id': payout.sender_batch_id,
            'email_subject': 'Hey! Subject!'
        },
        'items': [{
            'recipient_type': 'EMAIL',
            'amount': {
                'value': '12.34',
                'currency': 'USD'
            },
            'note': 'Uh... note.',
            'sender_item_id': payout.sender_batch_id,
            'receiver': 'doov@dave.deeve'
        }]}
    self.assertEqual(expected, payout.get_send_data())

  def test_successful_send(self):
    payout = Payout.objects.init_new_payout(
        pay_email='doov@dave.deeve', amount=Money('12.34', 'USD'),
        email_subject='Hey! Subject!', note='Uh... note.',
        when_should=str_to_tz_dt('2018-10-15 12:00'))

    api = Mock(spec=API)
    api.send_payout.return_value = SUCCESSFULL_SEND
    error_logger = Mock(spec=ErrorLogger)

    payout.send(api=api, error_logger=error_logger)

    self.assertEqual('PENDING', payout.batch_status)
    self.assertEqual('P8Z8TRV7P', payout.payout_batch_id)
    self.assertEqual(0, len(error_logger.log_error.call_args_list))

    # Test need_status_check while we're in here.
    self.assertTrue(payout in Payout.objects.need_status_check(
        str_to_tz_dt('2018-11-01 12:00')))
    not_sent_yet = Payout.objects.init_new_payout(
        pay_email='roov@rave.reeve', amount=Money('88.88', 'USD'),
        email_subject='blargh', note='stuff',
        when_should=str_to_tz_dt('2018-10-15 12:00'))
    self.assertFalse(not_sent_yet in Payout.objects.need_status_check(
        str_to_tz_dt('2018-11-01 12:00')))

  def test_failed_send(self):
    payout = Payout.objects.init_new_payout(
        pay_email='doov@dave.deeve', amount=Money('12.34', 'USD'),
        email_subject='Hey! Subject!', note='Uh... note.',
        when_should=str_to_tz_dt('2018-10-15 12:00'))

    api = Mock(spec=API)
    api.send_payout.return_value = FAILED_SEND
    error_logger = Mock(spec=ErrorLogger)

    payout.send(api=api, error_logger=error_logger)

    self.assertEqual('USER_BUSINESS_ERROR', payout.error_name)
    self.assertTrue(bool(payout.error_message))
    self.assertEqual(1, len(error_logger.log_error.call_args_list))

  def test_success_status(self):
    api = Mock(spec=API)
    api.get_status.return_value = SUCCESS_STATUS
    error_logger = Mock(spec=ErrorLogger)

    payout = get_test_payout(
        when_did=str_to_tz_dt('2018-12-15 12:00'),
        transaction_status='PENDING')
    check_status_background(
        api=api, nnow=str_to_tz_dt('2019-01-15 12:00'),
        error_logger=error_logger)

    payout.refresh_from_db()
    self.assertEqual(SUCCESS, payout.batch_status)
    self.assertEqual(payout.paypal_fee, Money('0.25', 'USD'))
    self.assertEqual('YD64339XCD88N', payout.payout_item_id)
    self.assertEqual(SUCCESS, payout.transaction_status)
    self.assertEqual('', payout.error_name)
    self.assertEqual('', payout.error_message)
    self.assertEqual('9AA07935LY8771919', payout.transaction_id)
    self.assertEqual(parse_datetime('2019-01-03T17:03:43Z'), payout.when_did)

  def test_error_status(self):
    api = Mock(spec=API)
    api.get_status.return_value = ERROR_STATUS
    error_logger = Mock(spec=ErrorLogger)
    notifier = Mock(spec=Notifier)

    payout = get_test_payout(
        when_did=str_to_tz_dt('2018-12-15 12:00'),
        transaction_status='PENDING',
        pay_email='dave@doov.dang')
    check_status_background(
        api=api, nnow=str_to_tz_dt('2019-01-15 12:00'),
        error_logger=error_logger, notifier=notifier)

    payout.refresh_from_db()
    self.assertEqual(SUCCESS, payout.batch_status)
    self.assertEqual(Money('0.25', 'USD'), payout.paypal_fee)
    self.assertEqual('5NWBQWQ5Z6EUQ', payout.payout_item_id)
    self.assertEqual('UNCLAIMED', payout.transaction_status)
    self.assertEqual('RECEIVER_UNREGISTERED', payout.error_name)
    self.assertEqual((
        'This receiver is not registered. You\'ll need to request them to '
        'sign up with PayPal to receive the payment.'), payout.error_message)
    self.assertEqual('21846482A3831715D', payout.transaction_id)
    self.assertEqual(parse_datetime('2018-02-28T17:10:34Z'), payout.when_did)
    to = [settings.ALERT_SERVICE_PROVIDER_NEEDS_PAYPAL]
    expected_alert = call(
        to, 'dave@doov.dang isn\'t signed up for Paypal', (
            'Could somebody please contact dave@doov.dang and encourage them '
            'to sign up for Paypal so we can pay them?'))
    self.assertEqual([expected_alert], notifier.notify.call_args_list)
