from collections import namedtuple

from django.urls import reverse

from guesty.models import GuestyReservation
from rentals.models import Rental
from reports.rent_revenue.util import (
    reservations_in_range, reservation_res_stats, pro_rated_res_stats)


class ReservationList(object):
  def __init__(self, rental_id, from_date, to_date):
    self.rental = Rental.objects.get(pk=rental_id)
    self.from_date = from_date
    self.to_date = to_date

  def get_res_deets_list(self):
    res_deets_list = []
    reservations = reservations_in_range(self.from_date, self.to_date).filter(
        rental=self.rental)
    for reservation in reservations:
      res_stats = reservation_res_stats(reservation)
      pro_rated = pro_rated_res_stats(
          reservation, self.from_date, self.to_date)

      if pro_rated.occupied_days > 0:
        # There might not be a guesty_reservation, as is the case with
        # the old booking.com reservations we manually imported.
        guesty_reservation = GuestyReservation.objects.filter(
            reservation=reservation).first()
        admin_url = None
        guesty_id = None
        if guesty_reservation:
          admin_url = guesty_reservation.admin_url()
          guesty_id = guesty_reservation.guesty_id
        stayd_web_url = reverse(
            'reservation_history', kwargs={'pk': reservation.pk})

        res_deets_list.append(ResDeetsForList(
            admin_url=admin_url,
            guesty_id=guesty_id,
            stayd_web_url=stayd_web_url,
            stayd_web_id=reservation.pk,
            guest_name=reservation.guest.get_name(),
            check_in=reservation.check_in,
            check_out=reservation.check_out,
            nights=res_stats.occupied_days,
            nights_in_range=pro_rated.occupied_days,
            percent_in_range=int(
                100.0 * pro_rated.occupied_days / res_stats.occupied_days),
            total_income=res_stats.total_income,
            total_income_in_range=pro_rated.total_income,
            cleaning_fees=res_stats.cleaning_fees,
            cleaning_fee_in_range=pro_rated.cleaning_fees,
            channel_fees=res_stats.channel_fees,
            channel_fee_in_range=pro_rated.channel_fees,
            taxes=res_stats.taxes,
            taxes_in_range=pro_rated.taxes))

    return res_deets_list


_res_deets_fields = [
    'admin_url',
    'guesty_id',
    'stayd_web_url',
    'stayd_web_id',
    'guest_name',
    'check_in',
    'check_out',
    'nights',
    'nights_in_range',
    'percent_in_range',
    'total_income',
    'total_income_in_range',
    'cleaning_fees',
    'cleaning_fee_in_range',
    'channel_fees',
    'channel_fee_in_range',
    'taxes',
    'taxes_in_range']


class ResDeetsForList(namedtuple('ResDeetsForList', _res_deets_fields)):
  pass
