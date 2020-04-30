""" Email (background CHeck EMAIL) the guest when we're dropping their
reservation due to invalid ids or failed background checks. This must all be
done without any user interface because these emails contain highly sensitive
information. """
from datetime import timedelta
from json import JSONDecodeError

from django.conf import settings
from django.db import models

from bgcheck.models.background_check import BackgroundCheck
from commands.models import background_command
from guest_messages.mandrill import Emailer
from reservations.models import Reservation
from util.timezone import now


FAILED_CHECK_MESSAGE = (
    'Dear {},\n\nWe use an outside professional service for criminal '
    'background checks on all applicants. Our third-party service notified us '
    'of a felony conviction. We made no further inquiry into the matter. '
    'However, due to building policy you don\'t qualify as a guest for this '
    'property. Should you wish to dispute the information, you have 60 days '
    'to notify us; and if you do so, we will look further into it and let you '
    'know what we find.\n\n'
    'We will cancel your reservation and fully refund you.')


""" DON'T create and send Chemails on BackgroundCheck post_save because one
time Tom accidentally clicked Fail, realized his mistake, and then clicked
Pass. So we should only send these after, say, they've fallen off the
bgchecks_for_vas list. """


@background_command
def send_chemails_background(nnow=None, emailer=None):
  nnow = nnow or now()
  for bgcheck in BackgroundCheck.objects.filter(
      completed_at__gte=nnow - timedelta(hours=24),
      completed_at__lte=nnow - timedelta(hours=1),
      passed=False):
    create_chemail_if_not_exists(bgcheck.reservation)
  for chemail in Chemail.objects.filter(when__isnull=True):
    chemail.send(emailer=emailer)


def create_chemail_if_not_exists(reservation):
  if not Chemail.objects.filter(reservation=reservation).exists():
    Chemail.objects.create(
        reservation=reservation, to=reservation.guest.email)


def send_test_chemail(reservation, to):
  chemail = Chemail.objects.create(reservation=reservation, to=to)
  chemail.send(ok_to_do_it_in_dev=True)
  return chemail


class Chemail(models.Model):
  """ Yeah, I want to keep this totally separate from everything so it never
  accidentally shows up in a user interface somewhere. Chemail is short for
  background check email. """
  reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE)
  when = models.DateTimeField(db_index=True, null=True, help_text=(
      'Set this when you send it.'))
  to = models.CharField(max_length=200, help_text=(
      'The email address we should send this to.'))
  send_attempts = models.PositiveIntegerField(default=0)

  def get_subject(self):
    building = self.reservation.rental.building
    return (
        'Regarding your recent reservation at {} in {} with Howard'.format(
            building.nickname, building.city))

  def send(self, emailer=None, ok_to_do_it_in_dev=False):
    emailer = emailer or Emailer()
    try:
      params = {'guest_first': self.reservation.guest.get_first_name()}
      emailer.send_email(
          self.get_subject(), self.to, params,
          settings.TEMPLATE_WE_MUST_CANCEL_DUE_TO_BGCHECK,
          ok_to_do_it_in_dev=ok_to_do_it_in_dev)
      self.when = now()
    except (JSONDecodeError, ConnectionError):
      self.send_attempts += 1
    self.save()
