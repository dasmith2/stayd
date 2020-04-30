""" This table doesn't make a lot of sense. I guess it can best be described as
the bill we send the guests based on the booking date. But then again it
includes refunds. But then again it doesn't include payments. It's basically
designed by Greg, but I have to admit, he didn't really seem to know what he
wanted. One time he told me he wanted one row per payment based on the payment
date, then he sent me an example CSV that had nothing to do with payments and
had 1 row per reservation line item. I asked him if he wanted refunds in the
table, and he said yes, 1 row per refund, and to use the airbnb sales category
and put the amount as negative, but the example CSV he sent used the cleaning
fee category and put the amount as positive. I smell confusion. My gut tells me
this table either doesn't get used or it needs a lot of work. """
from django.conf import settings
from django.shortcuts import reverse

from errors.models import notify
from netsuite.models.category_by_channel import CategoryByChannel
from reservations.models.money import (
    Reservation, Refund, ReservationLineItem, KNOWN_LINE_ITEM_NAMES)
from util.table import Table
from util.urls import keys_url


HEADERS = [
    'Date', 'Posting Date', 'External ID', 'Ref No', 'Vendor', 'Category',
    'Category ID', 'Location Name', 'Location ID', 'Amount']


def reservations_for_bill_table(from_date, to_date):
  return Reservation.objects.filter(
      ideal_payin__gt=0, booked_at__date__gte=from_date,
      booked_at__date__lt=to_date).select_related('rental', 'rental__location')


def _get_refunds_lookup(reservations):
  refunds_lookup = {}  # reservation -> list
  for refund in Refund.objects.filter(
      payment__reservation__in=reservations).select_related(
          'payment', 'payment__reservation'):
    res = refund.payment.reservation
    if res not in refunds_lookup:
      refunds_lookup[res] = []
    refunds_lookup[res].append(refund)
  return refunds_lookup


def _get_reservation_line_item_lookup(reservation):
  lookup = {}  # reservation -> list
  for rli in ReservationLineItem.objects.filter(
      reservation__in=reservation).order_by('pk').select_related(
          'reservation'):
    if rli.reservation not in lookup:
      lookup[rli.reservation] = []
    lookup[rli.reservation].append(rli)
  return lookup


def bill_table(reservations):
  table = Table(HEADERS)
  categories_by_channel_lookup = _get_categories_by_channel_lookup()
  refunds_lookup = _get_refunds_lookup(reservations)
  line_item_lookup = _get_reservation_line_item_lookup(reservations)
  for res in reservations:
    booked_at = res.booked_at
    location_id = None
    if res.rental.location_or_none:
      location_id = res.rental.location.location_id
    else:
      subject = 'What is the Location ID for {}?'.format(res.rental.nickname)
      message = keys_url(
          reverse('admin:netsuite_location_add') + '?rental={}'.format(
              res.rental.pk))
      notify(settings.ALERT_NETSUITE_CONFIGURATION_REQUIRED, subject, message)

    def _add_row(category, category_id, amount):
      table.create_row([
          booked_at.strftime('%m/%d/%Y'), booked_at.strftime('%B'),
          res.channel_id, res.channel_id, res.channel.lower(), category,
          category_id, res.rental.nickname, location_id, amount])

    categories = _get_categories_by_channel(
        res.channel, categories_by_channel_lookup)
    for line_item in line_item_lookup.get(res, []):
      category, category_id = _get_category_and_id(line_item.name, categories)
      # Channel fees are negative in our database.
      amount = abs(line_item.value.amount)
      _add_row(category, category_id, amount)

    for refund in refunds_lookup.get(res, []):
      # Refund amounts are positive in our database, but greg wants them
      # negative here.
      _add_row(
          categories.sales_category_name, categories.sales_category_id,
          -refund.amount.amount)

  return table


def _get_categories_by_channel_lookup():
  return dict([
      (cbc.channel, cbc) for cbc in CategoryByChannel.objects.all()])


def _get_category_and_id(line_item_name, categories):
  """ I built this by hand by digging through the database. """
  known = KNOWN_LINE_ITEM_NAMES()
  if known.is_rent(line_item_name):  # 4k of these
    return categories.sales_category_name, categories.sales_category_id
  elif known.is_cleaning(line_item_name):  # 4k of these
    return 'Cleaning Fee Income', 841
  elif known.is_channel_fee(line_item_name):  # 3k of these
    return categories.fee_category_name, categories.fee_category_id
  elif known.is_tax(line_item_name):  # 800 of these
    return 'Taxes & Licenses', 639
  # And then there's, like, 36 line_item_names with 30 or less, 25 of which
  # have only 1 instance. That's because people just enter free text, so
  # there's a "early checkin" and "Early Check-In Fee $50" kind of thing
  # happening. I'll just leave the category ID blank in these fringe cases.
  return line_item_name, None


def _get_categories_by_channel(channel, categories_by_channel_lookup):
  categories = categories_by_channel_lookup.get(channel, None)
  if not categories:
    subject = 'What are the Netsuite Categories for {}?'.format(channel)
    message = keys_url(
        reverse('admin:netsuite_categorybychannel_add') + '?channel={}'.format(
            channel))
    notify(settings.ALERT_NETSUITE_CONFIGURATION_REQUIRED, subject, message)
    categories = CategoryByChannel()
  return categories
