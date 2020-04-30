from reservations.models.money import (
    Payment, Refund, CreditCardFee, ReservationLineItem, KNOWN_LINE_ITEM_NAMES)
from util.table import Table, Cell


def get_revenue_details_table(building, from_date, to_date):
  table = Table([
      'Reservation', 'Guest', 'Amount', 'Paid at', 'Who got paid?',
      'CC fee', 'City "service fee"'])
  payments = get_payments(from_date, to_date).filter(
      reservation__rental__building=building).select_related(
          'reservation', 'reservation__guest').order_by('paid_at')
  cc_fee_lookup = get_cc_fee_lookup(payments)
  service_fee_lookup = get_service_fee_lookup(payments)
  for payment in payments:
    who_got_paid = '???'
    try:
      payment.charge
      who_got_paid = 'We did.'
    except Payment.charge.RelatedObjectDoesNotExist:
      pass
    reservation_cell = Cell(
        payment.reservation.channel_id, url=payment.reservation.admin_url())
    table.create_row([
        reservation_cell, payment.reservation.guest.get_name(),
        payment.amount, payment.paid_at.date(), who_got_paid,
        cc_fee_lookup.get(payment.pk, ''),
        service_fee_lookup.get(payment.pk, '')])
  return table


def get_cc_fee_lookup(payments):
  lookup = {}
  for fee in CreditCardFee.objects.filter(
      payment__in=payments).select_related('payment'):
    if fee.payment.pk not in lookup:
      lookup[fee.payment.pk] = fee.amount
    else:
      lookup[fee.payment.pk] += fee.amount
  return lookup


def get_service_fee_lookup(payments):
  """ Airbnb collects and remits all occupancy taxes, also sometimes refered to
  (incorrectly) as a sales tax. We never see that dollar amount. Now, on
  channels where we collect the payments, the situation is much more confused.
  On Booking.com we collect a "Service fee" which is roughly equivalent to what
  we fear it's possible we may have to remit in taxes. But we received advice
  that collecting and remiting taxes is the responsibility of the OTA (e.g.
  Booking.com) so we haven't remitted these values. To further complicate
  things, Guesty doesn't allow "Service fee" line items so these Booking.com
  service fees are labeled as "City tax" in Guesty. This is a pretty dicey
  situation because it makes it look like we're collecting a tax but not
  remitting it. So until we figure that whole situation out, that income is
  restricted.

  The "Service fee" is split across payments. So if the "service fee" line item
  is for $10, the total payin is expected to be $200, then a payment of $100
  will report $5 of the service fee. """
  reservations = set()
  payments_by_reservation = {}
  service_fee_lookup = {}
  for payment in payments:
    if payment.reservation.pk not in payments_by_reservation:
      payments_by_reservation[payment.reservation.pk] = []
    payments_by_reservation[payment.reservation.pk].append(payment)
    reservations.add(payment.reservation)
  for line_item in ReservationLineItem.objects.filter(
      name=KNOWN_LINE_ITEM_NAMES.CITY_TAX,
      reservation__in=reservations).select_related('reservation'):
    ideal = line_item.reservation.ideal_payin
    if ideal:
      for payment in payments_by_reservation.get(line_item.reservation.pk, []):
        amount = line_item.value * (payment.amount / ideal)
        service_fee_lookup[payment.pk] = amount
  return service_fee_lookup


def get_refund_details_table(building, from_date, to_date):
  table = Table(['Reservation', 'Guest', 'Amount', 'Created at'])
  for refund in get_refunds(from_date, to_date).filter(
      payment__reservation__rental__building=building).select_related(
          'payment', 'payment__reservation',
          'payment__reservation__guest').order_by('created_at'):
    reservation_cell = Cell(
        refund.payment.reservation.channel_id,
        url=refund.payment.reservation.admin_url())
    table.create_row([
        reservation_cell, refund.payment.reservation.guest.get_name(),
        refund.amount, refund.created_at.date()])
  return table


def get_payments(from_date, to_date):
  return Payment.objects.filter(
      reservation__is_test_reservation=False,
      reservation__rental__is_test_rental=False,
      reservation__rental__is_active=True,
      reservation__rental__building__is_active=True,
      paid_at__date__gte=from_date,
      paid_at__date__lt=to_date).select_related('charge')


def get_refunds(from_date, to_date):
  return Refund.objects.filter(
      payment__reservation__is_test_reservation=False,
      payment__reservation__rental__is_test_rental=False,
      payment__reservation__rental__is_active=True,
      payment__reservation__rental__building__is_active=True,
      created_at__date__gte=from_date, created_at__date__lt=to_date)
