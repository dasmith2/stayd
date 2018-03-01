## Get a token ##

https://www.paypal.com/us/selfhelp/article/how-do-i-get-an-access-token-ts2128

Note that their page has typos.

curl –v https://api.sandbox.paypal.com/v1/oauth2/token \
  -H "Accept: application/json" \
  -H "Accept-Language: en_US" \
  -u "AeOqD39LFAgOd06JwyVRq4upeEDx2sQF-hfOi8_UEf_pZYAGpwhcG6jgQ5CKk71LyQqBiOn5im1AACOf:EJ-XZfCuXZizF-nGVGN2AWVdIe0l23CHWCa71RV-pzXoUjIy8pYZVRCOdMEqbAXeflxuaWlKCOAN2oVs" \
  -d "grant_type=client_credentials"

{'access_token': 'A21AAGDB1Gdq_9iM6VFH895yhFQGPrP_ffyh3ca9_Bd1BavkuTfzP0FshHM1r0MqVAlDgY9pivuAPxCKOnBEqkAAC7bI__j9Q',
 'app_id': 'APP-80W284485P519543T',
 'expires_in': 32400,
 'nonce': '2018-03-01T17:20:33ZnHIkHmpusPv6Y-D5pb-goeVrZa3lIYG0iKl9CKIgfF4',
 'scope': 'https://uri.paypal.com/services/disputes/read-seller https://uri.paypal.com/services/subscriptions https://api.paypal.com/v1/payments/.* https://uri.paypal.com/services/disputes/read-buyer https://api.paypal.com/v1/vault/credit-card https://uri.paypal.com/services/applications/webhooks openid https://uri.paypal.com/payments/payouts https://uri.paypal.com/services/disputes/update-seller https://api.paypal.com/v1/vault/credit-card/.*',
 'token_type': 'Bearer'}

## Create payout ##

https://developer.paypal.com/docs/api/payments.payouts-batch/#payouts_create

curl -v -X POST https://api.sandbox.paypal.com/v1/payments/payouts \
-H "Content-Type: application/json" \
-H "Authorization: Bearer &lt;Access-Token-goes-here&gt;" \
-d '{
  "sender_batch_header": {
  "sender_batch_id": "2014021801",
  "email_subject": "You have a payout!",
  "email_message": "You have received a payout! Thanks for using our service!"
  },
  "items": [{
    "recipient_type": "EMAIL",
    "amount": {
    "value": "9.87",
    "currency": "USD"
    },
    "note": "Thanks for your patronage!",
    "sender_item_id": "201403140001",
    "receiver": "receiver@example.com"
  }]
}'

### success ###

{'batch_header': {
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

### failure ###
{'debug_id': 'f86c3504dc7b5',
 'details': [{'field': 'SENDER_BATCH_ID',
   'issue': 'Batch with given sender_batch_id already exists',
   'link': [{'encType': 'application/json',
     'href': 'https://api.sandbox.paypal.com/v1/payments/payouts/P8Z8TRV7PBBCE',
     'method': 'GET',
     'rel': 'self'}]}],
 'information_link': 'https://developer.paypal.com/docs/api/payments.payouts-batch/#errors',
 'message': 'User business error.',
 'name': 'USER_BUSINESS_ERROR'}

## Check status ##

https://developer.paypal.com/docs/api/payments.payouts-batch/#payouts_get

curl -v -X GET https://api.sandbox.paypal.com/v1/payments/payouts/P8Z8TRV7P \
-H "Content-Type: application/json" \
-H "Authorization: Bearer Access-Token-goes-here"

{'batch_header': {'amount': {'currency': 'USD', 'value': '1.0'},
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
    'message':
     "This receiver is not registered. You'll need to request them to
      sign up with PayPal to receive the payment.",
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
