from errors.models import log_error
from guesty.models import GuestyReservation
from reservations.models import Reservation
from util.clock import Clock
from front.models import Front, ContactInfo


class FrontContactUpdater(object):
  """ Let's say a guest gets a text from us. They respond to the text.
  Now we've got a message from some number in Front. Wouldn't it be nice
  if the admins could instantly see who that is and where they're staying?
  That's what this class is for. It updates the contact information associated
  with phone numbers in Front. """
  def __init__(self, front=Front(), clock=Clock()):
    self.front = front
    self.clock = clock

  def update_for_guest(self, guest):
    """ This should get called just when reservations get created to make sure
    there's something in the contact info. """
    reservations = Reservation.objects.filter(
        check_out__gt=self.clock.now(),
        guest=guest).order_by('-check_out')
    self._update_for_reservations(reservations, False)

  def update(self, verbose=False):
    """ This will update for all upcoming reservations. We call
    update_for_guest on every webhook now, so this is just a catch-up for
    when we need it. There's a management command called
    update_front_contacts. """
    reservations = Reservation.objects.filter(
        check_out__gt=self.clock.now()).order_by('-check_out')
    self._update_for_reservations(reservations, verbose)

  def _update_for_reservations(self, reservations, verbose):
    contact_updates = {}
    for reservation in reservations:
      contact_info = self._get_contact_info_for_reservation(reservation)
      if contact_info:
        contact_updates[reservation.guest.id] = contact_info
    self.front.set_contact_infos(list(contact_updates.values()), verbose)

  def _get_contact_info_for_reservation(self, reservation):
    name = '{} {}'.format(
        reservation.guest.full_name,
        reservation.listing.rental.nickname)
    date_format = '%Y-%m-%d %H:%M'
    description = 'checkin: {}\ncheckout: {}\ncity: {}'.format(
        reservation.get_check_in().strftime(date_format),
        reservation.get_check_out().strftime(date_format),
        reservation.listing.rental.city)
    email = reservation.guest.email
    phone = reservation.guest.phone
    guestyvations = GuestyReservation.objects.filter(reservation=reservation)
    if not guestyvations:
      message = (
          'Reservation {} doesn\'t have a GuestyReservation. '
          'I\'m trying to look up the GuestyReservation so I can create '
          'a link for front contact info.').format(reservation.pk)
      log_error('Missing GuestyReservation', message)
      return
    link = 'https://app.guesty.com/reservations/{}/guests'.format(
        guestyvations[0].guesty_id)
    return ContactInfo(
        name=name,
        description=description,
        link=link,
        phone=phone,
        email=email)
