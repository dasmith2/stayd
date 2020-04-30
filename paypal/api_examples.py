# flake8: noqa
SUCCESSFULL_SEND = {
 'batch_header': {
  'batch_status': 'PENDING',
  'payout_batch_id': 'P8Z8TRV7P',
  'sender_batch_header': {
    'email_subject': 'You just got paid by Stayd',
    'sender_batch_id': '1'}},
 'links': [{
  'encType': 'application/json',
  'href': 'https://api.sandbox.paypal.com/v1/payments/payouts/P8Z8TRV7P',
  'method': 'GET',
  'rel': 'self'}]}

FAILED_SEND = {
 'debug_id': 'f86c3504dc7b5',
 'details': [{'field': 'SENDER_BATCH_ID',
   'issue': 'Batch with given sender_batch_id already exists',
   'link': [{'encType': 'application/json',
     'href': 'https://api.sandbox.paypal.com/v1/payments/payouts/P8Z8TRV7PBBCE',
     'method': 'GET',
     'rel': 'self'}]}],
 'information_link': 'https://developer.paypal.com/docs/api/payments.payouts-batch/#errors',
 'message': 'User business error.',
 'name': 'USER_BUSINESS_ERROR'}


SUCCESS_STATUS = {'batch_header': {'payout_batch_id': 'FRCPL4RTS59P8',
  'batch_status': 'SUCCESS',
  'time_created': '2019-01-03T17:03:39Z',
  'time_completed': '2019-01-03T17:03:43Z',
  'sender_batch_header': {'sender_batch_id': '3_SM2GW',
   'email_subject': 'email_subject. We can modify this.'},
  'amount': {'currency': 'USD', 'value': '1.00'},
  'fees': {'currency': 'USD', 'value': '0.25'}},
 'items': [{'payout_item_id': 'YD64339XCD88N',
   'transaction_id': '9AA07935LY8771919',
   'transaction_status': 'SUCCESS',
   'payout_item_fee': {'currency': 'USD', 'value': '0.25'},
   'payout_batch_id': 'FRCPL4RTS59P8',
   'payout_item': {'recipient_type': 'EMAIL',
    'amount': {'currency': 'USD', 'value': '1.00'},
    'note': 'note. We can modify this.',
    'receiver': 'dasmith2@gmail.com',
    'sender_item_id': '3_SM2GW',
    'recipient_wallet': 'PAYPAL'},
   'time_processed': '2019-01-03T17:03:43Z',
   'links': [{'href': 'https://api.paypal.com/v1/payments/payouts-item/YD64339XCD88N',
     'rel': 'item',
     'method': 'GET',
     'encType': 'application/json'}]}],
 'links': [{'href': 'https://api.paypal.com/v1/payments/payouts/FRCPL4RTS59P8?page_size=1000&page=1',
   'rel': 'self',
   'method': 'GET',
   'encType': 'application/json'}]}

ERROR_STATUS = {'batch_header': {'amount': {'currency': 'USD', 'value': '1.0'},
  'batch_status': 'SUCCESS',
  'fees': {'currency': 'USD', 'value': '0.25'},
  'payout_batch_id': 'SWZCNHCAR7ST8',
  'sender_batch_header': {'email_subject': 'You just got paid by Stayd',
   'sender_batch_id': '5'},
  'time_completed': '2018-02-28T17:10:37Z',
  'time_created': '2018-02-28T17:10:21Z'},
 'items': [{'errors': {'details': [],
    'information_link':
    'https://developer.paypal.com/docs/api/payments.payouts-batch/#errors',
    'message': (
     'This receiver is not registered. You\'ll need to request them to '
     'sign up with PayPal to receive the payment.'),
    'name': 'RECEIVER_UNREGISTERED'},
   'links': [{'encType': 'application/json',
     'href':
     'https://api.sandbox.paypal.com/v1/payments/payouts-item/5NWWQ5Z6EUQ',
     'method': 'GET',
     'rel': 'item'}],
   'payout_batch_id': 'SWZCNHCAR7ST8',
   'payout_item': {'amount': {'currency': 'USD', 'value': '1.0'},
    'note': 'This is a note on an individual payment',
    'receiver': 'dasmith2@gmail.com',
    'recipient_type': 'EMAIL',
    'sender_item_id': '5'},
   'payout_item_fee': {'currency': 'USD', 'value': '0.25'},
   'payout_item_id': '5NWBQWQ5Z6EUQ',
   'time_processed': '2018-02-28T17:10:34Z',
   'transaction_id': '21846482A3831715D',
   'transaction_status': 'UNCLAIMED'}],
 'links': [{'encType': 'application/json',
   'href':
   'https://api.paypal.com/v1/payments/payouts/SR7ST8?page_size=10&page=1',
   'method': 'GET',
   'rel': 'self'}]}
