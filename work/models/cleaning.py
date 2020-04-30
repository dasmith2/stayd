""" There are two cases. We use independent cleaners or we use a cleaning
company.

You can't ask one independent cleaner to clean two rentals in the same amount
of time, but a combo rental is two or more rentals. So the rule is, one
cleaning per atom rental.  """
from collections import namedtuple
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models, connection
from django.db.models import Q, F
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.shortcuts import reverse

from commands.models import background_command
from errors.models import log_error, Notifier
from work.api import API
from work.models.cleaning_config import CleaningConfig
from work.models.message import (
    CLEAN_CO_CLEANING_NEEDS_CLEANER_ASAP, CHECKOUT_TIME_CHANGED_SO_REASSIGN,
    MessageSender, Message)
from work.models.rental import ProperlyRental
from work.models.work import (
    Work, CANCELED as WORK_CANCELED, CREATION_ERROR,
    WorkManager, remove_canceled_or_declined)
from work.models.worker import IndependentWorker
from work.models.work_type import WorkType, CLEANER
from rentals.models import Rental
from reservations.models import (
    Reservation, CONFIRMED, CANCELED as RES_CANCELED)
from util.object_lookup import get_object_lookup
from util.signals import post_sync
from util.timezone import parse_dt, now, tz_dt_to_str


@background_command
def create_cleanings_in_keys_background():
  """ This creates the cleanings in keys. """
  Cleaning.objects.create_in_keys()


JOBS_START_AFTER_CHECKOUT = timedelta(minutes=15)
# Usually, send out new cleanings at the same time each day. Happens to be noon
# at the moment.
SCHEDULE_INDEP_CLEANINGS_FOR_DAYS_AWAY = 7
SCHEDULE_WORK_CO_CLEANINGS_FOR_DAYS_AWAY = 14
# But sometimes a cleaning comes up and should be sent out immediately.
IMMEDIATELY_SCHEDULE_INDEP_CLEANINGS_FOR_DAYS_AWAY = (
    SCHEDULE_INDEP_CLEANINGS_FOR_DAYS_AWAY - 1)


class Cleanable(namedtuple(
    'Cleanable', 'reservation rental manual_cleaning')):
  """ A Cleanable is enough info to uniquely identify a time and place a
  cleaner could do a cleaning. Before combo rentals there was no need for this
  concept as a reservation was enough to uniquely identify a cleaning.

  Now that we don't resend jobs to people who canceled or declined, we should
  keep one cleaning per cleanable as opposed to making a new one.

  Reservation can be None as long as there's a manual_cleaning. """
  def get_rental(self):
    if self.manual_cleaning:
      return self.manual_cleaning.rental
    return self.rental

  def get_cleaning(self):
    if self.manual_cleaning:
      return self.manual_cleaning
    if self.reservation:
      return Cleaning.objects.filter(
          reservation=self.reservation, rental=self.get_rental()).first()

  def get_properly_rental(self):
    return self.get_rental().properlyrental_or_none

  def get_start_time(self):
    if self.manual_cleaning:
      return self.manual_cleaning.offered_start_time
    return Cleaning.objects.get_start_time(self.reservation)

  def rental_uses_independent_workers(self):
    # Note that this cleanable may represent a cleaning which is assigned to a
    # clean co worker. This function simply says whether the rental, by
    # default, uses independent workers.
    properly_rental = self.get_rental().properlyrental_or_none
    if properly_rental:
      return not properly_rental.clean_co
    return True

  def available_independent_cleaners(self):
    cleaning_config = CleaningConfig.objects.get_for_rental(self.get_rental())
    if not cleaning_config:
      return []
    duration = cleaning_config.cleaning_duration
    return remove_canceled_or_declined(
        self.get_cleaning(), IndependentWorker.objects.available(
            self.get_start_time(), duration,
            self.get_rental().building,
            WorkType.objects.get_work_type(CLEANER)))

  def init(self, api=None, nnow=None):
    cleaning = self.get_cleaning()
    if not cleaning:
      cleaning = Cleaning.objects.create(
          reservation=self.reservation,
          rental=self.get_rental(),
          offered_start_time=self.get_start_time())
    elif cleaning.status() not in (CREATION_ERROR, WORK_CANCELED):
      # This might happen if Guesty sends, like, 4 simultaneous webhooks.
      return
    elif cleaning.canceled_at:
      # The cleaning exists already. Maybe it was impermanently canceled.
      cleaning.reopen()
    cleaning.offered_start_time = self.get_start_time()
    cleaning.save()
    # If we use independent cleaners, init means create the cleaning object AND
    # immediately send it off to properly so the service providers can work it
    # out amongst themselves who gets this cleaning. If it's a workco
    # cleaning, then init simply means, create the object.
    if self.rental_uses_independent_workers():
      cleaning.offered_to.set(self.available_independent_cleaners())
    return cleaning


@receiver(post_sync, sender=Reservation)
def post_reservation_sync(sender, instance, *args, **kwargs):
  if settings.TEST or settings.PROD:
    Cleaning.objects.handle_res_sync(
        instance, kwargs.get('api', API()), nnow=kwargs.get('nnow', None),
        message_sender=kwargs.get('message_sender', None))


@receiver(post_save, sender=ProperlyRental)
def post_properly_rental_save_properly_rental(
    sender, instance, *args, **kwargs):
  # Somebody may have just saved a properly rental with a new cleaning company.
  # Upcoming cleanings may not exist yet because nobody's been around to clean
  # them...  until now! Quick, kick this off.
  if instance.clean_co:
    create_cleanings_in_keys_background()


@receiver(post_save, sender=CleaningConfig)
def post_properly_rental_save_cleaning_config(
    sender, instance, *args, **kwargs):
  # Somebody may have just saved a properly rental with a new cleaning company.
  # Upcoming cleanings may not exist yet because nobody's been around to clean
  # them...  until now! Quick, kick this off.
  if instance.clean_co_config:
    create_cleanings_in_keys_background()


class CleaningManager(WorkManager):
  def get_following_reservation_lookup(self, cleanings):
    # This is pretty much tested by
    # work.tests.test_clean_co#test_assign_cleanings_table which displays the
    # check in of the following reservation.
    active_cleanings = [
        clean for clean in cleanings if clean.status() != WORK_CANCELED]
    if not active_cleanings:
      return {}
    rentals = [cleaning.get_rental() for cleaning in active_cleanings]
    start_times = [
        cleaning.get_start_time() for cleaning in active_cleanings]
    if not start_times:
      return {}
    min_start_time = min(start_times)
    reservations = Reservation.objects.filter(
        rental__in=rentals,
        check_in__gt=min_start_time,
        status=CONFIRMED).order_by('check_in').select_related(
            'rental', 'rental__building')
    lookup = {}
    for cleaning in active_cleanings:
      for reservation in reservations:
        if reservation.rental == cleaning.get_rental() and (
            reservation.check_in > cleaning.get_start_time() and (
                cleaning not in lookup)):
          lookup[cleaning] = reservation
    return lookup

  def get_scheduled_cleanings(self, reservation):
    """ Sigh, from time to time properly will have some big weird problem and
    all the cleanings for that day will have creation errors. I want those to
    keep trying to recreate automatically. So a cleaning with a creation error
    isn't considered a valid cleaning.

    A cleaning company cleaning that isn't in properly yet is considered
    scheduled. """
    return reservation.cleaning_set.filter(canceled_at=None, creation_error='')

  def get_cleanables(self, reservation):
    if reservation.rental.is_combo_rental():
      to_return = []
      for rental in reservation.rental.is_combo_of.all():
        to_return.append(Cleanable(
            reservation=reservation, rental=rental, manual_cleaning=None))
      return to_return
    return [Cleanable(
        reservation=reservation, rental=reservation.rental,
        manual_cleaning=None)]

  def create_in_keys(self, nnow=None, api=API()):
    nnow = nnow or now()
    to_return = []
    for cleanable in self.cleanables_require_create_in_keys(nnow):
      to_return.append(cleanable.init(api=api, nnow=nnow))
    return to_return

  def get_start_time(self, reservation):
    if reservation.guest_enters_apartment():
      return reservation.get_reservation_end() + JOBS_START_AFTER_CHECKOUT

  def explain_why_cant_send_to_properly(self, cleanable):
    if not CleaningConfig.objects.get_for_rental(cleanable.rental):
      return '{} doesn\'t have a cleaning config'.format(
          cleanable.rental.nickname)
    if cleanable.get_start_time() < parse_dt(settings.PROPERLY_GOES_LIVE):
      return 'The cleaning is before properly goes live'
    if not cleanable.rental.properlyrental_or_none or not (
        cleanable.rental.properlyrental.is_configured()):
      return '{} doesn\'t have a Properly ID'.format(
          cleanable.rental.nickname)

  def explain_why_cant_create_cleanings_in_keys(self, reservation, nnow=None):
    """ This does a bunch of queries per reservation, so don't call this in a
    list. Rather, use def cleanables_require_create_in_keys for lists. Note
    that
    test_cleanables_require_create_and_explain_why_cant_create_cleanings
    tests these together. Note that even if a cleaning can't be sent to
    properly yet, in can still be initialized. """
    nnow = nnow or now()
    cleanings_required = self.get_cleanables(reservation)
    if len(
        self.get_scheduled_cleanings(reservation)) == len(cleanings_required):
      return 'This reservation has all its cleanings already.'
    if reservation.cleaning_set.filter(~Q(
        permanently_canceled_reason=''), canceled_at__isnull=False).exists():
      return 'This reservation has a permanently canceled cleaning'
    if reservation.status == RES_CANCELED and (
        reservation.canceled_at < reservation.check_in):
      return 'This reservation was canceled before check in.'
    if reservation.we_need_to_collect_more_money():
      return 'This reservation has an outstanding balance of {}'.format(
          reservation.get_balance_due())
    if not reservation.id_verified:
      return 'This guest\'s ID isn\'t verified'
    if not reservation.background_check_valid():
      return 'The background check is non-valid'  # Purposefully vague
    for cleanable in cleanings_required:
      # Cleaning companies, their whole job is to ensure there are cleaners
      # available.
      if cleanable.rental_uses_independent_workers():
        if not IndependentWorker.objects.for_building(
            reservation.rental.building, CLEANER):
          return 'No independent cleaners are configured for this building'
        cleaners_available = cleanable.available_independent_cleaners()
        if not cleaners_available:
          if len(cleanings_required) == 1:
            return (
                'This building has independent cleaners, but they\'re all '
                'busy')
          else:
            return (
                'No cleaners are available for at least 1 of the '
                '{} required cleanings.').format(len(cleanings_required))
      if cleanable.get_start_time() < nnow:
        return 'The cleaning time is in the past'
    too_distant = self.explain_why_cleaning_too_distant_to_create_in_keys(
        reservation, nnow=nnow)
    if too_distant:
      return too_distant

  def explain_why_cleaning_too_distant_to_create_in_keys(
      self, reservation, nnow=None):
    nnow = nnow or now()
    cleanings_required = self.get_cleanables(reservation)
    for cleanable in cleanings_required:
      if cleanable.rental_uses_independent_workers():
        if cleanable.get_start_time() > nnow + timedelta(
            days=SCHEDULE_INDEP_CLEANINGS_FOR_DAYS_AWAY):
          return 'The cleaning time is more than {} days away'.format(
              SCHEDULE_INDEP_CLEANINGS_FOR_DAYS_AWAY)
      else:
        if cleanable.get_start_time() > nnow + timedelta(
            days=SCHEDULE_WORK_CO_CLEANINGS_FOR_DAYS_AWAY):
          return 'The cleaning time is more than {} days away'.format(
              SCHEDULE_WORK_CO_CLEANINGS_FOR_DAYS_AWAY)

  def confirmed_no_cleaning(self, nnow=None, within_hours=48):
    """ Sometimes VAs will mess up the handling of a reservation, failing to
    toggle the id_verified switch after manually verifying an ID, say. So the
    reservation is happening and will need to be cleaned up after. But such a
    reservation looks pretty much identical to a fraudulent reservation where
    we don't want to create the cleaning. And who knows what other stuff could
    go wrong. So basically, return all reservations that look like they should
    have a cleaning in the next 48 hours, but for whatever reason, they don't
    have one. """
    nnow = nnow or now()
    # Note: could be the distant past.
    confirmed_cleaning_lt_48 = Q(
        status=CONFIRMED, check_out__lte=nnow + timedelta(hours=48))
    # Note the cleaning time based on cancelation is a bit more complicated
    # than what's appropriate for a SQL query, so this potentially pulls back
    # too many.
    canceled_cleaning_in_future = Q(
        canceled_at__gte=F('check_in')) & Q(
            canceled_at__gte=nnow - timedelta(days=1))
    cleaning_lt_48 = confirmed_cleaning_lt_48 | canceled_cleaning_in_future
    at_least_three_hours_old = Q(booked_at__lte=nnow - timedelta(hours=3))
    for reservation in Reservation.objects.filter(
        cleaning_lt_48, at_least_three_hours_old, cleaning__isnull=True,
        rental__is_test_rental=False, rental__is_active=True,
        check_out__gt=nnow):
      start_time = Cleaning.objects.get_start_time(reservation)
      if start_time and start_time >= nnow and start_time <= nnow + timedelta(
          hours=48):
        for cleanable in Cleaning.objects.get_cleanables(reservation):
          yield cleanable

  def cleanables_require_create_in_keys(self, nnow=None):
    """ Returns a list of cleanables that need to begin their cleaning journey.
    So that's cleanables for cleanings that look like they're definitely going
    to happen in the coming week, but either no Cleaning object yet exists for
    them, or if they do exist, there's something wrong with them like they're
    canceled or they didn't launch right.

    OK, if you're here, you may be asking yourself, "Why won't my cleaning get
    created?" Perhaps you're writing tests. Well before you pick this thing
    apart, start with
    Cleaning.objects.explain_why_cant_create_cleanings_in_keys( my_reservation,
    nnow=nnow)

    Stuff that can ought to be filtered out in SQL should be done in
    _non_atom_cleanables_require_create_in_keys and
    _atom_cleanables_require_create_in_keys. Stuff that makes more sense with
    Django ORM type logic goes here.

    Apologies for the raw sql. I couldn't come up with a good way to do
    LEFT OUTER JOIN (subselect) AS foo WHERE foo.bar IS NULL
    with the Django ORM. subselect here is cleanings that block the creation of
    new cleanings, which includes active existing cleanings and cleanings that
    were permanently canceled, but not cleanings that were canceled by service
    providers or in the properly web UI. """
    nnow = nnow or now()
    for cleanable in self._get_potential_cleanables_require_create_in_keys(
        nnow):
      if cleanable.reservation.we_need_to_collect_more_money():
        continue
      if not cleanable.reservation.background_check_valid():
        continue
      if cleanable.rental_uses_independent_workers():
        if not cleanable.available_independent_cleaners():
          continue
        # The rule is, x days away from CHECKOUT as opposed to cleaning start
        # time. It doesn't make much of a difference, so long as we're
        # consistent between this function and explain_
        if cleanable.get_start_time() > nnow + timedelta(
            SCHEDULE_INDEP_CLEANINGS_FOR_DAYS_AWAY):
          continue
      else:
        if cleanable.get_start_time() > nnow + timedelta(
            SCHEDULE_WORK_CO_CLEANINGS_FOR_DAYS_AWAY):
          continue
      yield cleanable

  def _get_potential_cleanables_require_create_in_keys(self, nnow=None):
    return list(
        self._non_atom_cleanables_require_create_in_keys(nnow=nnow)) + (
            self._atom_cleanables_require_create_in_keys(nnow=nnow))

  def _atom_cleanables_require_create_in_keys(self, nnow=None):
    """ If you find yourself printing out raw_sql and args in order to debug
    something, consider using
    Cleaning.objects.explain_why_cant_create_cleanings_in_keys(
        my_reservation, nnow=nnow) """
    return_me = []
    for reservation in self._atom_cleanables_require_create_in_keys_query(
        nnow=nnow):
      return_me.append(Cleanable(
          reservation=reservation, rental=reservation.rental,
          manual_cleaning=None))
    return return_me

  def _atom_cleanables_require_create_in_keys_query(self, nnow=None):
    nnow = nnow or now()

    raw_sql = ''.join([
        'SELECT res.* FROM ',
        'reservations_reservation AS res ',
        'JOIN rentals_rental AS rental ON rental.id = res.rental_id ',
        'JOIN work_properlyrental AS pr ON pr.rental_id = rental.id ',
        'LEFT OUTER JOIN rentals_rental_is_combo_of as is_combo_of ',
        'ON is_combo_of.from_rental_id = res.rental_id ',
        self.LEFT_OUTER_JOIN_CLEAN,
        'ON res.id = clean.reservation_id '
        '  AND res.rental_id = clean.rental_id ',
        'WHERE is_combo_of.from_rental_id IS NULL AND ',
        self.REQUIRE_CLEANING_WHERE])

    args = self._require_cleaning_raw_sql_args(nnow)
    return Reservation.objects.raw(raw_sql, args)

  # The point of this subselect is to find any existing cleanings that would
  # block the creation of a new cleaning, a.k.a. not canceled cleanings, and
  # permanently canceled cleanings. There are 2 canceled cases. Cleanings that
  # were canceled on properly for who knows what reason, which should be
  # rescheduled, and cleanings that were permanently canceled for a good reason
  # and should not be rescheduled.
  LEFT_OUTER_JOIN_CLEAN = (
      'LEFT OUTER JOIN ('
      '  SELECT clean.reservation_id, clean.rental_id '
      '  FROM work_cleaning AS clean '
      '  JOIN work_work AS work ON work.id = clean.work_ptr_id '
      #  A cleaning with a creation_error doesn't block new cleanings.
      '  WHERE work.creation_error = \'\' AND ('
      #  Permanently canceled cleanings block new cleanings.
      '  work.permanently_canceled_reason != \'\' '
      #    Not canceled cleanings block new cleanings.
      '    OR work.canceled_at IS NULL)) AS clean ')

  # We really check cleaning.get_start_time instead of reservation.check_out.
  REQUIRE_CLEANING_WHERE = (
      'clean.reservation_id IS NULL '
      'AND (('
      '  res.status = %s '
      '  AND res.check_out >= %s '
      '  AND res.check_out <= %s) '
      'OR ('
      '  res.status = %s and res.check_in < res.canceled_at)) '
      'AND res.id_verified is true '
      'ORDER BY res.check_out, rental_id;')

  def _require_cleaning_raw_sql_args(self, nnow):
    furthest = max(
        SCHEDULE_INDEP_CLEANINGS_FOR_DAYS_AWAY,
        SCHEDULE_WORK_CO_CLEANINGS_FOR_DAYS_AWAY)
    cutoff = nnow + timedelta(days=furthest)
    return [CONFIRMED, nnow, cutoff, RES_CANCELED]

  def _non_atom_cleanables_require_create_in_keys(self, nnow=None):
    """ If you find yourself printing out raw_sql and args in order to debug
    something, consider using
    Cleaning.objects.explain_why_cant_create_cleanings_in_keys(
        my_reservation, nnow=nnow) """
    nnow = nnow or now()

    raw_sql = ''.join([
        'SELECT res.id AS reservation_id, ',
        'is_combo_of.to_rental_id AS rental_id ',
        'FROM reservations_reservation AS res ',
        'JOIN rentals_rental_is_combo_of as is_combo_of ',
        '  ON is_combo_of.from_rental_id = res.rental_id ',
        'JOIN work_properlyrental AS pr '
        '  ON pr.rental_id = is_combo_of.to_rental_id ',
        self.LEFT_OUTER_JOIN_CLEAN,
        'ON res.id = clean.reservation_id AND ',
        'is_combo_of.to_rental_id = clean.rental_id ',
        'WHERE ',
        self.REQUIRE_CLEANING_WHERE])

    args = self._require_cleaning_raw_sql_args(nnow)

    res_ids = set()
    rental_ids = set()
    res_rental_pairs = []
    with connection.cursor() as cursor:
      cursor.execute(raw_sql, args)
      for (reservation_id, rental_id) in cursor.fetchall():
        res_ids.add(reservation_id)
        rental_ids.add(rental_id)
        res_rental_pairs.append((reservation_id, rental_id))
    res_lookup = get_object_lookup(Reservation, res_ids)
    rental_lookup = get_object_lookup(Rental, rental_ids)
    for reservation_id, rental_id in res_rental_pairs:
      yield Cleanable(
          reservation=res_lookup[reservation_id],
          rental=rental_lookup[rental_id], manual_cleaning=None)

  def uh_oh_unclaimed(self, start_within_hours=48, nnow=None):
    """ Return all cleanings that are more than 3 hours old, start within 48
    hours, and are unclaimed. """
    nnow = nnow or now()
    return self.filter(
        created_at__lte=nnow - timedelta(hours=3),
        # Just so we aren't notifying of cleanings that were supposed to happen
        # last week or something.
        offered_start_time__gte=nnow - timedelta(hours=1),
        offered_start_time__lte=nnow + timedelta(hours=start_within_hours),
        canceled_at__isnull=True,
        accepted_by__isnull=True)

  def taking_too_long(self, nnow):
    nnow = nnow or now()
    to_return = []
    for cleaning in self.todays_jobs(nnow).filter(
        started_at__isnull=False):
      to_time = cleaning.completed_at or nnow
      duration = to_time - cleaning.started_at
      if duration.seconds > 3 * 60 * 60 + 30 * 60:  # 3.5 hours
        to_return.append(cleaning)
    return to_return

  def still_cleaning_25_before_checkin(self, nnow):
    nnow = nnow or now()
    to_return = []
    for cleaning in self.todays_jobs(nnow).filter(
        completed_at__isnull=True):
      reservation = cleaning.get_following_reservation()
      if reservation and reservation.check_in <= nnow + timedelta(minutes=25):
        to_return.append(cleaning)
    return to_return

  def handle_res_sync(self, reservation, api, nnow=None, message_sender=None):
    """ The corner cases are when rentals and checkout times change. For
    instance, I've seen a reservation checkout time change at 5pm to 11am
    earlier that day. So even if it's after checkout now, we still have some
    thinking to do. """
    nnow = nnow or now()
    # Sometimes there's a mid-reservation cleaning. Right now that happens when
    # the rental changes mid-reservation. In the future we're going to
    # automatically give really long reservations a cleaning in the middle too.
    existing_checkout_cleanings = reservation.cleaning_set.filter(
        canceled_at__isnull=True,
        offered_start_time__date=reservation.check_out.date())
    existing_rentals = set([
        cleaning.rental for cleaning in existing_checkout_cleanings])
    should_rentals = set(reservation.rental.get_rentals())
    rental_changed = bool(existing_rentals - should_rentals) and (
        bool(should_rentals - existing_rentals))
    if rental_changed:
      self._handle_rental_change(
          reservation, existing_rentals, should_rentals, nnow=nnow)
    reservation.refresh_from_db()

    for rental in reservation.rental.get_rentals():
      cleanable = Cleanable(
          reservation=reservation, rental=rental, manual_cleaning=None)
      self.handle_cleanable_sync(
          cleanable, api, nnow=nnow, message_sender=message_sender)

  def _handle_rental_change(
      self, reservation, existing, should, nnow=None, api=None):
    nnow = nnow or now()
    lefts = list(existing - should)
    went_tos = list(should - existing)
    for i in range(len(lefts)):
      left = lefts[i]
      move_cleaning = reservation.cleaning_set.get(
          rental=left, offered_start_time__date=reservation.check_out.date())
      if i < len(went_tos):
        went_to = went_tos[i]
        move_cleaning.rental = went_to
        move_cleaning.save()
        mid_reservation_move = nnow > reservation.check_in
        if mid_reservation_move:
          use_cleaning_time = left.todays_checkout_time(nnow=nnow) + timedelta(
              minutes=15)
          if use_cleaning_time < nnow:
            use_cleaning_time += timedelta(days=1)
          Cleaning.objects.create(
              reservation=reservation,
              rental=left,
              offered_start_time=use_cleaning_time)
      else:
        reason = (
            'The reservation changed rentals and this cleaning is no longer '
            'needed')
        move_cleaning.cancel(reason, api=api)

  def handle_cleanable_sync(
      self, cleanable, api=None, nnow=None, message_sender=None):
    nnow = nnow or now()
    properly_rental = cleanable.rental.properlyrental_or_none
    if not properly_rental or not properly_rental.source_property_id:
      return
    config = properly_rental.cleaningconfig_or_none
    if not config:
      return

    reservation = cleanable.reservation
    cleaning = cleanable.get_cleaning()

    if cleaning:
      # Do we still need to clean, even if its canceled?
      if cleanable.reservation.guest_enters_apartment():
        if cleaning.get_start_time() != cleaning.offered_start_time:
          if cleaning.completed_at:
            raise Exception(
                'Why are we about to update the offered start time of '
                'completed cleaning {}?'.format(cleaning.pk))
          if cleaning.created_in_properly():
            cleaning.impermanent_cancel(api=api)
            cleanable.init(api=api, nnow=nnow)
          elif cleaning.uses_work_co():
            if cleaning.offered_to.exists():
              to = cleaning.get_work_co().alerts_email
              tz = cleanable.rental.building.time_zone
              old_time = tz_dt_to_str(cleaning.offered_start_time, tz)
              new_time = tz_dt_to_str(cleaning.get_start_time(), tz)
              content = (
                  'The cleaning at {} on {} was assigned to {}. Since the '
                  'checkout time changed to {}, the cleaning needs to '
                  'be reassigned.\n\n{}').format(
                      cleanable.rental.nickname, old_time,
                      cleaning.offered_to.first().name, new_time,
                      settings.CLEAN_CO_SERVER)
              Message.objects.create_and_send_email(
                  to, CHECKOUT_TIME_CHANGED_SO_REASSIGN, content, cleaning,
                  message_sender=message_sender)
              cleaning.offered_to.set([])
            cleaning.offered_start_time = cleaning.get_start_time()
            cleaning.save()
          else:
            cleaning.offered_start_time = cleaning.get_start_time()
            cleaning.save()
      elif cleaning.status != WORK_CANCELED:
        # No sense cleaning a rental that will never get dirty in the first
        # place.
        cleaning.cancel(
            'The reservation is now {}'.format(reservation.status), api)
    elif Cleaning.objects.explain_why_cant_create_cleanings_in_keys(
        reservation, nnow=nnow):
      pass
    elif cleanable.get_start_time() <= nnow + timedelta(
        days=IMMEDIATELY_SCHEDULE_INDEP_CLEANINGS_FOR_DAYS_AWAY):
      required = Cleaning.objects.cleanables_require_create_in_keys(nnow)
      for cleanable_need in required:
        if cleanable_need == cleanable:
          cleanable.init(api=api, nnow=nnow)


class Cleaning(Work):
  reservation = models.ForeignKey(
      Reservation, on_delete=models.PROTECT, null=True, help_text=(
          'The reservation this cleaning happens after.'))
  rental = models.ForeignKey(
      Rental, on_delete=models.PROTECT, help_text=(
          'A single reservation can have multiple cleanings at different '
          'rentals. If the rental changes mid reservation, 2 cleanings will '
          'now be necessary, one at the old rental ASAP after the change, '
          'and one at the new rental at checkout. A reservation for a combo '
          'unit causes 1 cleaning per rental.'))
  reviewed_by = models.ForeignKey(
      User, on_delete=models.PROTECT, null=True, blank=True, help_text=(
          'Who compared the confirmation photos to the example photos?'))
  reviewed_at = models.DateTimeField(
      null=True, blank=True, help_text='When did reviewed_by review?')

  objects = CleaningManager()

  class Meta:
    ordering = ['-offered_start_time']

  def save(self, *args, **kwargs):
    if int(bool(self.reviewed_by)) + int(bool(self.reviewed_at)) == 1:
      raise Exception(
          'Either set both or neither of reviewed_by and reviewed_at')
    super().save(*args, **kwargs)

  def invoice_prefix(self):
    return 'cl'

  def tax_rate(self):
    if self.uses_work_co():
      return self.get_work_co().services_tax_rate
    return 0

  def get_rental(self):
    return self.rental

  def get_cleaning_checklist(self):
    return self.rental.properlyrental.cleaningconfig.cleaning_checklist

  def is_manually_scheduled(self):
    return not self.reservation

  def is_scheduled_per_a_reservation(self):
    return self.reservation

  def reschedule(self, api=None, nnow=None, message_sender=None):
    why_cant_reschedule = None
    if self.is_scheduled_per_a_reservation():
      if Cleaning.objects.explain_why_cleaning_too_distant_to_create_in_keys(
          self.reservation, nnow=nnow):
        # Keys will create this cleaning in due time. No need to alert.
        return
      why_cant_reschedule = (
          Cleaning.objects.explain_why_cant_create_cleanings_in_keys(
              self.reservation, nnow=nnow))
    can_reschedule = not why_cant_reschedule
    if can_reschedule:
      if self.uses_work_co():
        self.offered_to.set([])
        self.accepted_by = None
        self.save()
      # init will affect this cleaning, but not this object exactly
      self.get_cleanable().init(api=api, nnow=nnow)
      # Hence, refresh here.
      self.refresh_from_db()

  def was_canceled_by_worker(self, message_sender=None, **kwargs):
    if self.uses_work_co():
      self._alert_work_co_needs_new_cleaner(message_sender=message_sender)
    super().was_canceled_by_worker(message_sender=message_sender, **kwargs)

  def was_declined(self, worker, message_sender=None):
    if self.uses_work_co():
      if worker.pk == self.offered_to.first().pk and (
          self.offered_to.count() == 1):
        self._alert_work_co_needs_new_cleaner(message_sender=message_sender)
        self.offered_to.set([])
      else:
        log_error(
            'Declined clean co cleaning should have exactly one offered_to',
            '{} has {}'.format(self.pk, list(self.offered_to.all())))
    super().was_declined(worker)

  def _alert_work_co_needs_new_cleaner(self, message_sender=None):
    # This means you can call this on declined, canceled, or canceled but
    # properly never sent us who accepted it.
    worker = self.accepted_by or self.offered_to.first()

    message_sender = message_sender or MessageSender()
    to = self.get_work_co().alerts_email
    message = (
        '{} canceled their cleaning at {} on {}. Please schedule '
        'somebody new ASAP!').format(
            worker.name, self.get_rental().nickname,
            self.offered_start_time.date())
    message_sender.create_and_send_email(
        to, CLEAN_CO_CLEANING_NEEDS_CLEANER_ASAP, message, self)

  def get_work_co(self):
    cleaner = self.accepted_by or self.offered_to.first()
    if cleaner:
      return cleaner.get_child_class_instance().get_work_co()
    rental = self.get_rental()
    if rental.properlyrental_or_none:
      return self.rental.properlyrental.clean_co

  def uses_work_co(self):
    return bool(self.get_work_co())

  def uses_independent_workers(self):
    return not self.uses_work_co()

  def get_cleanable(self):
    if self.reservation:
      return Cleanable(
          rental=self.get_rental(), reservation=self.reservation,
          manual_cleaning=None)
    return Cleanable(
        rental=self.get_rental(), reservation=None, manual_cleaning=self)

  def can_send_to_properly(self):
    return not Cleaning.objects.explain_why_cant_send_to_properly(
        self.get_cleanable())

  def alert_problem(self, subject, message, notifier=None):
    notifier = notifier or Notifier()
    use_message = '{}\n\n{}'.format(self.keys_url(), message)
    notifier.notify(
        self.reservation.rental.building.alerts_email, subject, use_message)

  def url(self):
    return '/admin/work/cleaning/{}/change/'.format(self.pk)

  def get_expected_duration(self):
    config = self.get_config()
    if not config:
      raise Exception('Theres no cleaning checklist for rental {}'.format(
          self.reservation.rental.nickname))
    return config.cleaning_duration

  def get_cleaning_history_url(self):
    return reverse('cleaning_history_detail', kwargs={'pk': self.pk})

  def get_following_reservation(self, following_reservation_lookup=None):
    # If this cleaning never happened, then there's no following reservation by
    # definition.
    if following_reservation_lookup is None:
      following_reservation_lookup = (
          Cleaning.objects.get_following_reservation_lookup([self]))
    return following_reservation_lookup.get(self, None)

  def get_config(self):
    return CleaningConfig.objects.get_for_rental(self.get_rental())

  def get_booking(self):
    return self.get_cleanable().get_booking()

  def get_deadline(self):
    raise Exception(
        'I believe cleanings should always be fixed and therefore '
        'get_deadline should never get called.')

  def alert_unaccepted_late_start(self):
    # Cleanings happen on a tight schedule.
    return True

  def get_source_property_id(self):
    return self.get_config().properly_rental.get_source_property_id()

  def get_properly_checklist_ids(self, api=None):
    config = self.get_config()
    if not config or not config.properly_checklist_id:
      raise Exception('Rental {} needs a properly cleaning checklist.'.format(
          self.get_rental()))
    return [config.properly_checklist_id]

  def get_message(self):
    config = self.get_config()
    return config and config.message

  def get_source_booking_id(self):
    booking = self.get_booking()
    # A few times now the booking.create API calls all started failing. So we
    # can't necessarily rely on bookings being in place but we still want
    # cleanings to go out.
    if booking and not booking.creation_error:
      return booking.get_source_booking_id()

  def should_offer_to(self):
    if self.uses_work_co():
      raise Exception(
          'There is no should_offer_to when it\'s a cleaning company '
          'cleaning.')
    return self.get_cleanable().available_independent_cleaners()

  def get_title(self):
    return 'Cleaning'

  def get_start_time(self):
    if self.reservation:
      return Cleaning.objects.get_start_time(self.reservation)
    return self.offered_start_time

  def get_readable_work_title(self):
    return 'a cleaning'

  def can_review(self):
    return self.didslide_set.exists()

  def review_button(self):
    return '<a href="{}" class="button">Review</a>'.format(
        reverse('review_cleaning', kwargs={'pk': self.pk}))

  def __repr__(self):
    return '<Cleaning {}: {} {}>'.format(
        self.pk, self.get_rental().nickname, self.pretty_status())
