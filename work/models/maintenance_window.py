""" This is to help Tom cobble together his inventory management system. It
emails a list of which units don't have a guest in them between 2 and 4 today.
In other words, units with a vacancy or a turnover. Service providers cross
reference this email with some spreadsheet that's got a list of what's missing
per unit. """
from collections import namedtuple
from datetime import timedelta

from rentals.models import Rental
from reservations.models import Reservation, CONFIRMED
from util.timezone import now


def available_today(nnow=None):
  nnow = nnow or now()
  rentals = set(Rental.objects.filter(
      is_active=True, combo_unit_description='', is_test_rental=False))
  for res in Reservation.objects.filter(
      check_in__date__lt=nnow.date(), check_out__date__gt=nnow.date(),
      status=CONFIRMED, is_test_reservation=False):
    for rental in res.rental.get_rentals():
      # You could have a reservation that isn't marked as a test reservation in
      # a rental that's marked as a test rental.
      if rental in rentals:
        rentals.remove(rental)
  return sorted(list(rentals), key=lambda x: x.full_address)


class MaintenanceWindow(
    namedtuple(
        'MaintenanceWindow', 'start_at has_checkout next_check_in')):

  """ A maintenance window is between 11am and 4pm, the time between
  reservations. Whether or not that night has a vacancy is important in some
  cases, like if you need to give the paint a chance to dry or something.
  Whether or not the maintenance window has a reservation on either side of it
  is also important, because you don't want to book maintenance in the middle
  of nowhere and block a valuable long running reservation. """

  def is_vacant_night(self):
    return not self.next_check_in or (
        self.start_at.date() < self.next_check_in.date())

  def before_or_after_reservation(self):
    return self._before_or_after_reservation(self.start_at.date())

  def vacant_night_before_or_after_reservation(self):
    if not self.is_vacant_night():
      raise Exception(
          'Only ask about reservations after a vacant night if there\'s '
          'actually a vacant night')
    return self._before_or_after_reservation(
        self.start_at.date() + timedelta(days=1))

  def _before_or_after_reservation(self, target_next_checkin):
    return self.has_checkout or (
        self.next_check_in and (
            self.next_check_in.date() == target_next_checkin))


def maintenance_windows(rental, in_next_x_days, reservations=None, nnow=None):
  """ Wow, surprisingly tricky. Return a list of MaintenanceWindows which
  describe which days have a gap between reservations, and which of those gaps
  are right next to a reservation and which of those gaps are followed by a
  vacant night. """

  nnow = nnow or now()
  cutoff = nnow + timedelta(days=in_next_x_days)
  # gaps has to pull back a little extra data before and after the window we're
  # curious about. Then the windows can correctly say if they're on a check out
  # or before a vacant night and check in.
  got_gaps = gaps(
      rental, in_next_x_days + 2, reservations=reservations, nnow=nnow)
  to_return = []
  on = None
  # If we hit no gaps, we were in a reservation the whole time.
  in_reservation = True
  for gap in got_gaps:
    # The maintenance window starts 15 minutes after the guest checks out.
    on = gap.check_out + timedelta(minutes=15)
    has_checkout = True
    while on <= cutoff and (not gap.next_check_in or on <= gap.next_check_in):
      if nnow <= on:
        to_return.append(MaintenanceWindow(
            on, has_checkout, gap.next_check_in))
      on += timedelta(days=1)
      has_checkout = False
    in_reservation = bool(gap.next_check_in)
  while not in_reservation and on <= cutoff:
    to_return.append(MaintenanceWindow(on, False, None))
    on += timedelta(days=1)
  return to_return


Gap = namedtuple('Gap', 'check_out next_check_in')


def gaps(rental, in_next_x_days, reservations=None, nnow=None):
  """ Return all the gaps between reservations starting with today's check out
  time. Gaps are set to the local time of the rental. """
  nnow = nnow or now()
  if reservations is None:
    reservations = Reservation.objects.reservations_in_range(
        nnow, nnow + timedelta(days=in_next_x_days))

  check_in_and_out_dates = _check_in_and_out_dates(rental, reservations)
  gaps = []

  todays_checkout_time = rental.todays_checkout_time(nnow=nnow)

  last_span = None
  for span in check_in_and_out_dates + [None]:
    if last_span:
      if span:
        gaps.append(Gap(last_span.check_out, span.check_in))
      elif last_span.check_out <= nnow + timedelta(days=in_next_x_days):
        gaps.append(Gap(last_span.check_out, None))
    elif span is None:  # a.k.a. a totally empty calendar
      gaps.append(Gap(todays_checkout_time, None))
    elif todays_checkout_time < span.check_in:
      gaps.append(Gap(todays_checkout_time, span.check_in))
    last_span = span
  return _set_gaps_timezone(gaps, rental.building)


def _set_gaps_timezone(gaps, building):
  to_return = []
  for gap in gaps:
    check_out = gap.check_out
    if check_out:
      check_out = building.set_timezone(check_out)
    next_check_in = gap.next_check_in
    if next_check_in:
      next_check_in = building.set_timezone(next_check_in)
    to_return.append(Gap(check_out, next_check_in))
  return to_return


def _check_in_and_out_dates(rental, reservations):
  CheckInAndOut = namedtuple('CheckInAndOut', 'check_in check_out')
  in_and_outs = []
  for res in reservations:
    # combo rental reservations are rare. Don't bother optimizing this.
    if res.confirmed() and rental in res.rental.get_rentals():
      in_and_outs.append(CheckInAndOut(res.check_in, res.check_out))
  return list(sorted(in_and_outs, key=lambda x: x.check_in))
