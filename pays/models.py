"""
These classes oversee sending and receiving money.
"""
from datetime import datetime

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from djmoney.models.fields import MoneyField
from djmoney.money import Money

from util import money
from pays.paypal_api import PaypalAPI


class PayableEmail(models.Model):
  """
  This is so we can send a test dollar to somebody to make sure
  they receive payments in Paypal.
  """
  email = models.TextField()

  @classmethod
  def send_test_dollar_via_paypal_to_email(cls, email):
    existing = PayableEmail.objects.filter(email=email)
    if existing.count() > 0:
      use_email = existing[0]
    else:
      use_email = PayableEmail.objects.create(email=email)
    return use_email.send_test_dollar_via_paypal()

  def send_test_dollar_via_paypal(self):
    assert self.email, 'You have to set the email before you can send'
    payout = PaypalPayout.init_new_payout(
        self,
        Money(1, 'USD'),
        self.email,
        'Stayd sent you one dollar',
        ('Stayd sent you a test payment of one dollar. Now we know we can pay '
         'you!'))
    payout.send()
    return payout

  def __repr__(self):
    return (f'{self.__class__.__name__}({self.email!r}, {self.pk!r})')


class Payout(models.Model):
  """
  This table should contain records of all the money we pay to other
  people.
  """
  who_to_pay_content_type = models.ForeignKey(
      ContentType, on_delete=models.CASCADE)
  who_to_pay_object_id = models.PositiveIntegerField()
  who_to_pay = GenericForeignKey(
      'who_to_pay_content_type', 'who_to_pay_object_id')
  amount = MoneyField(max_digits=10, decimal_places=2, default_currency='USD')
  when = models.DateTimeField(auto_now_add=True)


class PaypalPayout(Payout):
  """
  This table should contain records of every time we send somebody money
  through Paypal.

  Paypal keeps a distinction between a payout batch and a payout item. There's
  really no advantage to putting multiple items in the same batch. The fees are
  the same either way and it's not a performance issue. So we'll just do one
  item per batch because then we can have one less class/database table/join
  on our end.

  There's a race here. Paypal assumes you're going to send multiple items in
  the same batch so they don't return data synchronously, at least not any
  more. You must make a separate call to get the status and such. If this
  becomes a problem then we'll have to split up the mechanism that sends
  the payment and the mechanism that checks the status. For now, things run
  smoothly enough when we pretend it's synchronous.

  See https://www.paypal.com/us/webapps/mpp/merchant-fees for fees. It's a flat
  fee of .25 per USD payout in the USA. That's not per batch, that's per item.
  """
  fee = MoneyField(max_digits=10, decimal_places=2, default_currency='USD')
  email = models.TextField()
  email_subject = models.TextField(
      help_text="We can set this to whatever we want.")
  note = models.TextField(help_text="We can set this to whatever we want.")
  payout_batch_id = models.CharField(
      max_length=30, help_text=(
          "Set by Paypal. We only put one payout_item in each batch, "
          "which explains some of the redundancy."))
  sender_batch_id = models.CharField(
      max_length=30, help_text=(
          "Set by us. Each batch and each item gets an id from us and "
          "from Paypal, which explains yet more of the redundancy."))
  payout_item_id = models.CharField(max_length=30, help_text=(
      "Set by Paypal. We always do one payout item in one batch."))
  sender_item_id = models.CharField(max_length=30, help_text="Set by us.")
  transaction_id = models.CharField(
      max_length=30, help_text=(
          "Set by Paypal on the item level. This is maybe important?"))
  transaction_status = models.CharField(max_length=30, help_text=(
      "Set by Paypal on the item level. This is important."))
  batch_status = models.CharField(max_length=30, help_text=(
      "Set by Paypal on the batch level. This can be SUCCESS, "
      "PROCESSING, or PENDING (that I know of)."))
  error_name = models.TextField(help_text=(
      "Set on the item level. This is important-ish, but error_message "
      "is more helpful."))
  error_message = models.TextField(help_text=(
      "Set on the item level. This is important."))

  paypal_api = PaypalAPI()

  @classmethod
  def init_new_payout(cls, who_to_pay, amount, email, email_subject, note):
    payout = PaypalPayout.objects.create(
        who_to_pay=who_to_pay,
        amount=amount,
        email=email,
        email_subject=email_subject,
        note=note)
    # sender_batch_id and sender_item_id just need to be unique. Because
    # we only put one item in every batch it's ok to use the same id for both.
    # Because tests run on fresh databases, using self.pk alone is
    # insufficient.
    unique_id = '{}-{}'.format(
        payout.pk, datetime.now().strftime('%Y%m%d%H%M%S'))
    payout.sender_batch_id = unique_id
    payout.sender_item_id = unique_id
    payout.save()
    return payout

  def send(self):
    send_data = {
        "sender_batch_header": {
            "sender_batch_id": self.sender_batch_id,
            "email_subject": self.email_subject
        },
        "items": [{
            "recipient_type": "EMAIL",
            "amount": {
                "value": money.number_only_format(self.amount),
                "currency": str(self.amount.currency)
            },
            "note": self.note,
            "sender_item_id": self.sender_item_id,
            "receiver": self.email
        }]
    }

    data = self.paypal_api.send_payout(send_data)

    if 'batch_header' in data:
      batch_header = data['batch_header']

      self.batch_status = batch_header['batch_status']
      self.payout_batch_id = batch_header['payout_batch_id']
      self.save()
    else:
      self.error_name = 'API_ERROR'
      self.error_message = '{}'.format(data)
      self.save()

  def check_status(self):
    data = self.paypal_api.get_status(self.payout_batch_id)
    batch_header = data['batch_header']
    self.batch_status = batch_header['batch_status']
    fees = batch_header['fees']
    self.fee = Money(float(fees['value']), fees['currency'])
    item = data['items'][0]
    # It's called errors but it's not a list, just a single error.
    if 'errors' in item:
      error = item['errors']
      self.error_name = error['name']
      self.error_message = error['message']
    self.payout_item_id = item['payout_item_id']
    self.transaction_status = item['transaction_status']
    if self.transaction_status != 'PENDING':
      self.transaction_id = item['transaction_id']
    return self
