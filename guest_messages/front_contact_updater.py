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

  def update_for_guest(self, guest, ok_to_do_it_in_dev=False):
    """ Update for guest instead of reservation because front contact info
    contains reservation info, and if a guest has more than 1 upcoming
    reservation we want it to reflect the soonest one. """
    reservation = Reservation.objects.filter(
        check_out__gt=self.clock.now(),
        guest=guest).order_by('check_out').first()
    if not reservation:
      reservation = Reservation.objects.filter(
          guest=guest).order_by('-check_out').first()
    contact_info = self._get_contact_info_for_reservation(reservation)
    return self.front.set_contact_info(contact_info)

  def _get_contact_info_for_reservation(self, reservation):
    name = '{} {}'.format(
        reservation.guest.full_name,
        reservation.rental.nickname)
    date_format = '%Y-%m-%d %H:%M'
    description = 'checkin: {}\ncheckout: {}\ncity: {}'.format(
        reservation.get_check_in().strftime(date_format),
        reservation.get_check_out().strftime(date_format),
        reservation.rental.city)
    return ContactInfo(
        name=name,
        description=description,
        link=reservation.guesty_url(),
        phone=reservation.guest.phone,
        email=reservation.guest.email)
