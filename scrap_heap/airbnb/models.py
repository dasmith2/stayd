"""
I assume that reservations are already in our system when this runs, which
makes sense. By the time a reservation appears in this csv, it's already
started, at least. So if a reservation started and keys didn't know about it
yet, we've got bigger problems.

But you can check this assertion by, like,
assertEqual(0, ReservationPayout.objects.filter(
    reservation__isnull=True).count())
"""
from collections import namedtuple
import csv
from datetime import datetime, timedelta

from django.db import models, connection
from django.shortcuts import reverse
from djmoney.models.fields import MoneyField
from djmoney.money import Money

from commands.models import background_command
from reservations.models import Reservation
from util.object_lookup import get_pairs
from util.rm_old import RmOldManager
from util.timezone import now
from xxero.models.transactions import Transaction


def missing_reservations():
  """ Return all channel_ids for reservations that an airbnb csv referenced,
  but we don't have in our database. This isn't actually used anywhere, but I
  created it to demonstrate how to find them and remove the temptation to put
  a nullable Reservation foreign key in ReservationPayout. """
  with connection.cursor() as cursor:
    cursor.execute(
        """
        SELECT respay.channel_id FROM
        airbnb_reservationpayout AS respay
        LEFT OUTER JOIN reservations_reservation AS res
        ON respay.channel_id =  res.channel_id
        WHERE res.id IS NULL;
        """)
    return [row[0] for row in cursor.fetchall()]


class PayoutManager(models.Manager):
  def match_payouts_to_transactions(self):
    query = (
        'SELECT pay.id AS payout_id, '
        'transact.id AS transaction_id '
        'FROM airbnb_payout AS pay '
        'JOIN xxero_transaction AS transact '
        'ON pay.amount = transact.amount '
        'AND pay.date <= transact.when '
        # Transactions typically show up a few days after airbnb says it paid
        # out.
        'AND transact.when <= pay.date + interval \'4 days\' '
        'LEFT OUTER JOIN airbnb_payout AS existing_pay '
        'ON transact.id = existing_pay.transaction_id '
        'WHERE pay.transaction_id IS NULL '
        'AND existing_pay.id IS NULL;')
    # You could have 2 almost identical payouts that both match the same
    # transaction in the same upload, in which case this SQL query will do,
    # like, (payout1, transaction), (payout2, transaction)
    seen_transaction_already = set()
    for payout, transaction in get_pairs(query, Payout, Transaction):
      if transaction not in seen_transaction_already:
        seen_transaction_already.add(transaction)
        payout.transaction = transaction
        payout.save()

        reservations = []
        for res_payout in payout.reservationpayout_set.all():
          reservation = res_payout.get_reservation()
          if reservation:
            reservations.append(res_payout.get_reservation())
        payout.transaction.reservations.set(reservations)


class Payout(models.Model):
  """ This comes from the csv export from Airbnb detailing when each
  reservation paid out. """
  date = models.DateField(
      help_text='When did the payout happen?', db_index=True)
  amount = MoneyField(
      max_digits=10, decimal_places=2, default_currency='USD', help_text=(
          'Comes from the Paid Out column of the csv.'))
  note = models.TextField(help_text=(
      'For example, "Transfer to *****8228". Comes from the details column of '
      'the csv.'))
  transaction = models.OneToOneField(
      Transaction, on_delete=models.PROTECT, null=True, blank=True, help_text=(
          'transaction.reservations ties the actual reservations to real '
          'financial transactions. If transaction isnt populated here, it '
          'means that we didnt get that payout, somebody else did.'))

  objects = PayoutManager()


class ReservationPayout(models.Model):
  """ Reservation HMPY33PDYA for instance got paid out in two separate
  payments.

  The reservations themselves, if they exist, are stored in
  xxero.models.transactions.Transaction#reservations. """
  payout = models.ForeignKey(Payout, on_delete=models.PROTECT)
  channel_id = models.CharField(max_length=100, db_index=True, help_text=(
      'This isnt a foreign key to reservation on purpose. I can imagine '
      'scenarios where we import an Airbnb csv that references reservations '
      'we dont actually have in our database.'))
  amount = MoneyField(
      max_digits=10, decimal_places=2, default_currency='USD', help_text=(
          'Usually, but not always, this is the full amount of the '
          'reservation.'))

  def get_reservation(self):
    return Reservation.objects.filter(channel_id=self.channel_id).first()


class ResolutionAdjustment(models.Model):
  """ I'm just lumping Resolution Payouts in here too. As far as I can tell the
  only difference is that the amount is positive for Resolution Payouts and
  negative for Resolution Adjustments. """
  date = models.DateField(help_text='When does the csv say this happened?')
  amount = MoneyField(
      max_digits=10, decimal_places=2, default_currency='USD', help_text=(
          'Comes from the Paid Out column of the csv. '
          'This is typically negative.'))
  note = models.TextField(help_text=(
      'For example, "Resolution adjustment for resolution 10654307". '
      'Comes from the details column of the csv.'))
  payout = models.ForeignKey(Payout, on_delete=models.PROTECT)


class Other(models.Model):
  """ Not totally clear on what these are. """
  name = models.CharField(max_length=100, default='Tax Withholding')
  payout = models.ForeignKey(Payout, on_delete=models.PROTECT)
  channel_id = models.CharField(max_length=100, db_index=True, help_text=(
      'This isnt a foreign key to reservation on purpose. I can imagine '
      'scenarios where we import an Airbnb csv that references reservations '
      'we dont actually have in our database.'))
  amount = MoneyField(max_digits=10, decimal_places=2, default_currency='USD')


@background_command
def retry_raw_uploads_background():
  for raw in RawUpload.objects.filter(
      handled_at__isnull=True, created_at__gte=now() - timedelta(days=14)):
    raw.handle()


class RawUpload(models.Model):
  text = models.TextField(help_text='The raw text string from the file.')
  created_at = models.DateTimeField(auto_now_add=True, db_index=True)
  handled_at = models.DateTimeField(null=True, blank=True)

  objects = RmOldManager()

  def rows(self):
    return csv.reader(self.text.split('\n'))

  def handle(self):
    to_return = _handle_upload_airbnb_csv_rows(self.rows())
    self.handled_at = now()
    self.save()
    return to_return

  def url(self):
    return reverse('see_airbnb_csv_upload', kwargs={'pk': self.pk})


AirbnbCSVResult = namedtuple(
    'AirbnbCSVResult', 'date amount channel_id')


def _handle_upload_airbnb_csv_rows(csv_rows):
  """ csv_rows is a list of lists such as a csv reader.

  See example rows in test_handle_upload_airbnb_csv. """
  results = []
  rows = list(csv_rows)
  channel_ids = []
  for row in rows:
    if row and row[1] == 'Reservation':
      channel_ids.append(row[2])
  last_payout = None
  resolution_adjustment_names = [
      'Resolution Adjustment', 'Resolution Payout',
      'Cancellation Fee Refund']
  for row in rows:
    if not row:  # Probably the end of the file
      continue
    if row[1] == 'Type':  # Header row.
      continue
    dte = datetime.strptime(row[0], '%m/%d/%Y').date()
    if row[1] == 'Payout':
      amount = Money(row[11], 'USD')
      note = row[7]
      results.append(AirbnbCSVResult(
          date=dte, amount=amount, channel_id=None))
      last_payout = Payout.objects.get_or_create(
          date=dte, amount=amount, note=note)[0]
    elif row[1] == 'Reservation':
      channel_id = row[2]
      amount = Money(row[10], 'USD')
      ReservationPayout.objects.get_or_create(
          payout=last_payout, channel_id=channel_id, amount=amount)[0]
      results.append(AirbnbCSVResult(
          date=None, amount=None, channel_id=channel_id))
    elif row[1] in resolution_adjustment_names:
      amount = Money(row[10], 'USD')
      note = row[7]
      ResolutionAdjustment.objects.get_or_create(
          date=dte, amount=amount, note=note, payout=last_payout)
    else:
      channel_id = row[2]
      amount = Money(row[10], 'USD')
      Other.objects.get_or_create(
          name=row[1], payout=last_payout, channel_id=channel_id,
          amount=amount)[0]
  Payout.objects.match_payouts_to_transactions()
  return results
