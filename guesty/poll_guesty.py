""" One of our cleaning companies walked into a unit, the guest was still in
the shower! Well it turned out the reservation was extended, and Guesty never
sent a webhook, so Keys never updated the cleaning time. This week we've had
a few incidents like that. I just got back from manually syncing a
reservation that never sent a webhook ever. It's become clear to me we need
a sophisticated polling mechanism just for backup for when webhooks are
messed up. """
from datetime import timedelta, date
import time

from django.db.models import Q

from commands.models import background_command
from errors.models import log_error
from guesty.api import GuestyAPI
from guesty.guesty import sync_reservation
from guesty.models import GuestyReservation, ReservedReservation
from reservations.models.money import Reservation, CONFIRMED
from reservations.syncer import ReservationManagerIsDown
from util.timezone import now


@background_command
def poll_reserved_reservations(api=None, use_sync_reservation=None):
  api = api or GuestyAPI()
  use_sync_reservation = use_sync_reservation or sync_reservation
  for reserved in ReservedReservation.objects.all():
    try:
      res_data = api.get_one(Reservation, reserved.guesty_id)
      if res_data['status'] != 'reserved':
        use_sync_reservation(reserved.guesty_id)
        reserved.delete()
    except ReservationManagerIsDown:
      pass  # Ugh, fine. We'll just circle around in an hour.


@background_command
def poll_guesty(verbose=False):
  poll_all_confirmed_within_a_month(verbose=verbose)
  poll_created_last_week(verbose=verbose)


@background_command
def poll_all_confirmed_within_a_month(verbose=False):
  """ This only works on reservations that we already know about. I slapped
  this together to quick try and pull down all the recent-ish reservations. But
  then I noticed, like, half the requests failing with 502 status and content
  'An invalid response was received from the upstream server'. Guesty is having
  a rough week.

  This function maybe ought to run once or twice a day as some kind of
  fail-safe IN ADDITION to syncing expecting payments, which runs hourly so is
  trying to be a bit more punctual and selective. """
  not_recently_synced = Q(last_synced_at__isnull=True) | Q(
      last_synced_at__lt=now() - timedelta(hours=2))
  for res in Reservation.objects.filter(
      not_recently_synced, status=CONFIRMED,
      check_out__gt=now() - timedelta(days=30),
      check_in__lt=now() + timedelta(days=30)):
    _try_really_hard_to_sync_reservation(
        res.guestyreservation.guesty_id, verbose=verbose)


@background_command
def poll_created_last_week(verbose=False, from_date=None, to_date=None):
  limit = 25
  skip = 0
  guesty_ids = []
  latest_results = _poll_created_last_week_helper(
      skip, limit, from_date=from_date, to_date=to_date)
  while len(latest_results):
    guesty_ids.extend([result['_id'] for result in latest_results])
    skip += len(latest_results)
    latest_results = _poll_created_last_week_helper(
        skip, limit, from_date=from_date, to_date=to_date)

  for guesty_id in guesty_ids:
    if GuestyReservation.objects.filter(guesty_id=guesty_id).exists():
      if verbose:
        print('We already know about {}'.format(guesty_id))
    else:
      res = _try_really_hard_to_sync_reservation(guesty_id, verbose=False)
      if res:
        if verbose:
          print('Discovered a new reservation! {}'.format(guesty_id))
        else:
          subject = 'Reservation discovered with NO webhooks'
          message = (
              'Ive since imported it, but you might wanna inform guesty about '
              'https://app.guesty.com/reservations/{}/summary on '
              'https://support.guesty.com/en/contact').format(guesty_id)
          log_error(subject, message, always_new_error=True)


def _poll_created_last_week_helper(skip, limit, from_date=None, to_date=None):
  from_date = from_date or date.today() - timedelta(days=7)
  to_date = to_date or date.today() + timedelta(days=1)
  for i in range(3):
    try:
      return GuestyAPI().get_many(
          type_of_thing=Reservation, skip=skip, limit=limit,
          from_date=from_date, to_date=to_date)
    except ReservationManagerIsDown:
      pass
  raise ReservationManagerIsDown('Sigh')


def _try_really_hard_to_sync_reservation(guesty_id, verbose=False):
  while True:
    try:
      if verbose:
        print(guesty_id)
      return sync_reservation(guesty_id)
    except ReservationManagerIsDown:
      if verbose:
        print('Reservation manager is down')
      time.sleep(1)


@background_command
def poll_reservations_expecting_payment():
  """ Learned a few lessons the hard way. First, we have to poll guesty
  reservations because they don't notify us when payment is received. I found
  that out the hard way, but also, our rep just confirmed that. We need to know
  if payment was received in order to determine if we should send SMSs asking
  for payment, for instance. But, syncing should be decoupled from tasks. I
  used to sync reservations before sending messages, but this a) slowed
  send_guest_messages down too much and b) lots of stuff is triggered by
  post_sync, and if any of that stuff had errors, messages wouldn't go out. """
  try:
    for reservation in Reservation.objects.expecting_payments():
      reservation.sync()
      reservation.refresh_from_db()
  except ReservationManagerIsDown:
    pass  # Ugh, fine, we'll just try again later.
