from collections import namedtuple

from django.urls import reverse

from guesty.models import GuestyReservation
from rentals.models import Rental
from reports.rent_revenue.util import (
    total_days_and_within_from_to, reservations_in_range,
    reservation_charges_and_fees, pro_rated_charges_and_fees)


class ReservationList(object):
  def __init__(self, rental_id, from_date, to_date):
    self.rental = Rental.objects.get(pk=rental_id)
    self.from_date = from_date
    self.to_date = to_date

  def get_res_deets_list(self):
    res_deets_list = []
    for reservation in reservations_in_range(self.from_date, self.to_date):
      (total_days, within) = total_days_and_within_from_to(
          reservation, self.from_date, self.to_date)

      if within > 0:
        # There might not be a guesty_reservation, as is the case with
        # the old booking.com reservations we manually imported.
        guesty_reservation = GuestyReservation.objects.filter(
            reservation=reservation).first()
        guesty_url = None
        guesty_id = None
        if guesty_reservation:
          guesty_url = guesty_reservation.guesty_url()
          guesty_id = guesty_reservation.guesty_id
        stayd_web_url = reverse(
            'reservation_history', kwargs={'pk': reservation.pk})

        charges_and_fees = reservation_charges_and_fees(reservation)
        pro_rated = pro_rated_charges_and_fees(
            charges_and_fees, 1.0 * within / total_days)

        res_deets_list.append(ResDeetsForList(
            guesty_url=guesty_url,
            guesty_id=guesty_id,
            stayd_web_url=stayd_web_url,
            stayd_web_id=reservation.pk,
            guest_name=reservation.guest.get_name(),
            check_in=reservation.check_in,
            check_out=reservation.check_out,
            nights=total_days,
            nights_in_range=within,
            percent_in_range=int(100.0 * within / total_days),
            total_charges=charges_and_fees.total_charges,
            total_charges_in_range=pro_rated.total_charges,
            cleaning_fee=charges_and_fees.cleaning_fee,
            cleaning_fee_in_range=pro_rated.cleaning_fee,
            channel_fee=charges_and_fees.channel_fee,
            channel_fee_in_range=pro_rated.channel_fee))

    return res_deets_list


_res_deets_fields = [
    'guesty_url',
    'guesty_id',
    'stayd_web_url',
    'stayd_web_id',
    'guest_name',
    'check_in',
    'check_out',
    'nights',
    'nights_in_range',
    'percent_in_range',
    'total_charges',
    'total_charges_in_range',
    'cleaning_fee',
    'cleaning_fee_in_range',
    'channel_fee',
    'channel_fee_in_range']


class ResDeetsForList(namedtuple('ResDeetsForList', _res_deets_fields)):
  pass
