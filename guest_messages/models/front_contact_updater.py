from django.db import models
from django.dispatch import receiver
from util.timezone import now

from errors.models import Notifier
from front.models import (
    Front, BadContactInfoException,
    ContactInfoNeedsPushing as FrontContactInfoNeedsPushing)
from guest_messages.models.message import BadContactInfo
from reservations.models import Reservation
from util.clock import Clock
from util.signals import post_sync


@receiver(post_sync, sender=Reservation)
def post_sync(sender, instance, *args, **kwargs):
  if instance.confirmed() and instance.check_out > now():
    FrontContactUpdater().update_for_reservation_or_alert(instance)


class FrontContactUpdater(object):
  """ Let's say a guest gets a text from us. They respond to the text.
  Now we've got a message from some number in Front. Wouldn't it be nice
  if the VAs could instantly see who that is and where they're staying?
  That's what this class is for. It updates the contact information associated
  with phone numbers in Front. """
  def __init__(self, front=Front(), clock=Clock(), notifier=Notifier()):
    self.front = front
    self.clock = clock
    self.notifier = notifier

  def update_for_reservation_or_alert(self, reservation):
    self.update_for_contact_info_or_alert(
        self._contact_info_for_guest(reservation.guest))

  def update_for_contact_info_or_alert(self, contact_info):
    try:
      # If set_contact_info encounters a 502 or something, it simply calls
      # contact_info.save(). Then circle_back_around_failed_contact_info_pushes
      # will see it.
      return self.front.set_contact_info(contact_info)
    except BadContactInfoException as ex:
      BadContactInfo.objects.handle_bad_contact_info_exception(
          ex, contact_info.reservation, notifier=self.notifier)

  def circle_back_around_failed_contact_info_pushes(
      self, verbose=False, ok_to_do_it_in_dev=False):
    for contact_info in ContactInfoNeedsPushing.objects.all():
      if verbose:
        print('Retrying {}\'s contact info'.format(contact_info.name))
      if self.update_for_contact_info_or_alert(contact_info):
        contact_info.delete()
        if verbose:
          print('Success.')
      elif verbose:
        print('Failed attempt number {}.'.format(contact_info.push_attempts))

  def _contact_info_for_guest(self, guest, ok_to_do_it_in_dev=False):
    """ Update for guest instead of reservation because front contact info
    contains reservation info, and if a guest has more than 1 upcoming
    reservation we want it to reflect the soonest one. """
    reservation = Reservation.objects.filter(
        check_out__gt=self.clock.now(),
        guest=guest).order_by('check_out').first()
    if not reservation:
      reservation = Reservation.objects.filter(
          guest=guest).order_by('-check_out').first()
    return self._get_contact_info_for_reservation(reservation)

  def _get_contact_info_for_reservation(self, reservation):
    name = '{} {}'.format(
        reservation.guest.full_name,
        reservation.rental.nickname)
    date_format = '%Y-%m-%d %H:%M'
    description = 'checkin: {}\ncheckout: {}\ncity: {}'.format(
        reservation.get_check_in().strftime(date_format),
        reservation.get_check_out().strftime(date_format),
        reservation.rental.building.city)
    return ContactInfoNeedsPushing(
        name=name,
        description=description,
        link=reservation.admin_url(),
        phone=reservation.guest.phone,
        email=reservation.guest.email,
        reservation=reservation)


class ContactInfoNeedsPushing(FrontContactInfoNeedsPushing):
  """ If any of these are saved in the database, that means they were
  unsuccessfully sent to front and must be tried again. Once they are
  successful they should be deleted. """
  reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE)
