from django.db import models
from django.db.models import Q

from errors.models import log_error
from work.models.rental import properly_datetime_format
from rentals.models import Rental
from reservations.models import Reservation
from util.html_status_codes import get_json
from util.timezone import now


class BookingManager(models.Manager):
  def handle_res_sync(self, reservation, api, nnow=None):
    """ This is wired up in clean.py so it can make sure to call this before
    possibly creating cleanings. """
    nnow = nnow or now()
    if reservation.confirmed():
      return self.create_bookings(reservation, api)

  def get_create_booking_data(self, booking):
    res = booking.reservation
    properly_rental = booking.get_properly_rental()
    if not properly_rental:
      raise Exception(
          'The ProperlyRental for rental {} doesnt exist yet'.format(
              res.rental.pk))

    title = 'Reservation for {}'.format(res.guest.get_name())
    guest = {'sourceId': str(res.guest.channel_id)}
    # Properly definitely requires a firstName. Not totally sure about lastName
    # but you understand my paranoia.
    if res.guest.first_name:
      guest['firstName'] = res.guest.first_name
    else:
      guest['firstName'] = 'nofirstname'
    if res.guest.last_name:
      guest['lastName'] = res.guest.last_name
    else:
      guest['lastName'] = 'nolastname'
    return {
        'sourcePropertyId': properly_rental.get_source_property_id(),
        'sourceBookingId': booking.get_source_booking_id(),
        'startDate': properly_datetime_format(res.check_in),
        'endDate': properly_datetime_format(res.check_out),
        'title': title,
        'numberOfGuests': 1,
        'guestDetails': [guest]}

  def create_bookings(self, reservation, api, print_curl=False):
    to_return = []
    rentals = list(reservation.rental.get_rentals())
    for booking in self.filter(
        ~Q(rental__in=rentals), reservation=reservation):
      booking.cancel(api)
    for rental in rentals:
      properly_rental = rental.properlyrental_or_none
      if properly_rental and properly_rental.is_configured():
        to_return.append(self.create_booking(
            rental, reservation, api, print_curl=print_curl))
    return to_return

  def create_booking(self, rental, reservation, api, print_curl=False):
    booking = self.filter(rental=rental, reservation=reservation).first()
    if not booking:
      source_booking_id = self.get_ideal_source_booking_id(reservation, rental)
      booking = Booking(
          reservation=reservation, rental=rental,
          source_booking_id=source_booking_id)
    if not booking.booking_id:
      booking_data = self.get_create_booking_data(booking)
      got_json = get_json(
          api.booking_create(booking_data, print_curl=print_curl))
      if 'booking.create' in got_json:
        booking.booking_id = got_json['booking.create'][0]['bookingId']
        booking.save()
      else:
        # You can't save the booking without a unique nonempty booking_id.
        log_error('Weird booking.create response', '{} returned {}'.format(
            booking_data, got_json))
    return booking

  def get_ideal_source_booking_id(self, reservation, rental):
    if reservation.rental.is_combo_rental():
      return '{}_{}'.format(reservation.channel_id, rental.pk)
    return reservation.channel_id


class Booking(models.Model):
  """ The whole point of the Booking class is to show some reservation details
  in the properly calendar at https://app.getproperly.com/#/calendar?_k=g8fuee
  """
  booking_id = models.CharField(unique=True, max_length=200, help_text=(
      'This comes from Properly in the response to the booking.create call.'))
  reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE)
  rental = models.ForeignKey(
      Rental, on_delete=models.CASCADE, help_text=(
          'Now that we got combo rentals, a reservation isnt necessarily '
          'enough information to say what rental a booking is for.'))
  creation_confirmed = models.DateTimeField(null=True, blank=True)
  creation_error = models.TextField(null=True, blank=True)
  source_booking_id = models.CharField(max_length=200, default='', help_text=(
      'This used to just be self.reservation.channel_id but things got more '
      'complicated after the switch to combo rentals.'))

  objects = BookingManager()

  def get_source_booking_id(self):
    """ Bookings also have a sourceId a.k.a. sourceBookingId, as per properly's
    dubious design decision to require us to assign ids to almost all objects
    refered to in the API. """
    if self.source_booking_id:
      return self.source_booking_id
    to_return = Booking.objects.get_ideal_source_booking_id(
        self.reservation, self.rental)
    self.source_booking_id = to_return
    self.save()
    return to_return

  def cancel(self, api):
    return api.booking_cancel(self.booking_id)

  def change_reservation_dates(self, start_date, end_date, api):
    data = {
        'bookingId': self.booking_id,
        'changes': {
            'startDate': properly_datetime_format(start_date),
            'endDate': properly_datetime_format(end_date)}}
    return api.booking_changed(data)

  def get_properly_rental(self):
    return self.rental.properlyrental_or_none

  def __repr__(self):
    return '<Booking {}: {} {}>'.format(
        self.pk, self.reservation.check_in.date(), self.rental.nickname)
