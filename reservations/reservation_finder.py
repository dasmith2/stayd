import re

from guests.models import GuestPhoneNumber
from reservations.models import Reservation


class ReservationFinder(object):
  def find(self, query):
    """ This sometimes returns a query set and sometimes returns a list,
    so beware. """
    query = query.strip()
    return (
        self._q_is_reservation_id_reservation(query) or
        self._q_is_guesty_id_reservation(query) or
        self._q_is_guesty_url_reservation(query) or
        self._q_is_guest_full_name_reservation(query) or
        self._q_is_guest_first_name_reservation(query) or
        self._q_is_guest_last_name_reservation(query) or
        self._q_is_guest_phone_number_reservation(query) or
        self._q_is_channel_id_reservation(query))

  def _q_is_reservation_id_reservation(self, query):
    try:
      return Reservation.objects.filter(pk=int(query))
    except ValueError:
      pass

  def _q_is_guesty_id_reservation(self, query):
    return self._guesty_id_to_reservations(query)

  def _q_is_guesty_url_reservation(self, query):
    # https://app.guesty.com/reservations/5af60144ae3e0505d9e56647/guests
    found = re.compile(r'reservations/(\w+)/').search(query)
    if found:
      return self._guesty_id_to_reservations(found.groups()[0])

  def _q_is_guest_full_name_reservation(self, query):
    return Reservation.objects.filter(guest__full_name__iexact=query).order_by(
        '-check_out')

  def _q_is_guest_first_name_reservation(self, query):
    return Reservation.objects.filter(
        guest__first_name__iexact=query).order_by(
        '-check_out')

  def _q_is_guest_last_name_reservation(self, query):
    return Reservation.objects.filter(guest__last_name__iexact=query).order_by(
        '-check_out')

  def _q_is_guest_phone_number_reservation(self, query):
    reservations = []
    phone = GuestPhoneNumber.objects.numbers_only(query)
    if not phone or len(phone) < 10:
      return []
    for phone_number in GuestPhoneNumber.objects.filter(
        numbers_only__contains=phone):
      for reservation in Reservation.objects.filter(guest=phone_number.guest):
        reservations.append(reservation)
    return list(reversed(sorted(reservations, key=lambda res: res.check_out)))

  def _q_is_channel_id_reservation(self, query):
    return Reservation.objects.filter(channel_reservation_id=query)

  def _guesty_id_to_reservations(self, guesty_id):
    from guesty.models import GuestyReservation
    guesty_reservation = GuestyReservation.objects.filter(
        guesty_id=guesty_id).first()
    if guesty_reservation:
      return [guesty_reservation.reservation]
