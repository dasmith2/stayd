""" Schedule(verb): to assign a Ticket to a Maintenance job which is offered to
service providers. "Keys scheduled the broken water pipe Ticket right away, and
Bob accepted the job."

Turns out, it's no fun to manually schedule jobs to solve problems. It's like,
wait, what problems do we have? How urgent are they, who's available, when are
the rentals available? This file right here is the heart of a very valuable
project. It gets us that much closer to sipping mohitos on beaches while this
thing practically runs itself.

This file is for scheduling tickets. Pretty much everything else ticket related
goes in work.models.ticket
"""
import calendar
from collections import namedtuple
from datetime import timedelta
from pytz import UTC

from django.conf import settings
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver

from commands.models import background_command
from errors.models import ErrorLogger, log_error
from rentals.models import UNAVAILABLE
from reservations.models import Reservation
from work.models.maintenance_window import maintenance_windows
from work.models.message import MessageSender, Message, DELAYED_TICKET, EMAIL
from util.object_lookup import get_pairs
from util.timezone import now, tz_dt_to_str
from work.api import API
from work.models.maintenance_checklist import get_checklist_id_from_url
from work.models.maintenance import Maintenance
from work.models.not_scheduled_reason import not_scheduled_reason_finder
from work.models.sla import (
    NOW, URGENT, NEXT_CHECKOUT, NEXT_VACANT_NIGHT, NEXT_VISIT, DONT_SCHEDULE)
from work.models.ticket import (
    Ticket,
    PRIORITIZED, COMPLETE, INCOMPLETE, DELAYED,
    THIS_TICKET_LACKS_SLA)
from work.models.work import ACCEPTED, CANCELED, FLEXIBLE, FIXED
from work.models.worker import IndependentWorker


@background_command
def schedule_background(next_checkout_days_in_advance=3, api=None, nnow=None):
  return schedule(
      next_checkout_days_in_advance=next_checkout_days_in_advance, api=api,
      nnow=nnow)


@receiver(post_save, sender=Ticket)
def ticket_post_save(sender, instance, *args, **kwargs):
  """ post_save is triggered automatically from the bowels of Django and
  there's no way I know of to add anything to the kwargs that gets used there.

  So in order to test the parts of this function that call apis, I have to call
  this function directly. """

  _set_maintenance_fields(instance)

  if settings.TEST and not kwargs.get('ok_to_run_in_tests', False):
    return
  _schedule_emergency_immediately(instance, **kwargs)
  _cancel_if_all_dont_schedule_or_complete(instance, **kwargs)


def _set_maintenance_fields(ticket):
  """ What rental is a maintenance for? Ideally, we could just check the
  tickets, and indeed that's how I programmed it originally. But then we hit a
  corner case. A job that somebody started and completed, but the ticket wasn't
  completed, so the ticket got added to a different job, and now there's a work
  payment against a job with no rental information and the pay service
  providers page broke. So I'm afraid we have to normalize a bit here and
  maintain a copy of the rental and title on the maintenance level. """
  if ticket.maintenance:
    maintenance = ticket.maintenance
    if maintenance.rental and maintenance.rental != ticket.rental:
      raise Exception((
          'Trying to add a ticket whose rental doesnt match the maintenance '
          'rental'), ticket, ticket.maintenance)
    maintenance.rental = ticket.rental
    maintenance.title = maintenance.get_title()
    maintenance.save()


def _cancel_if_all_dont_schedule_or_complete(ticket, **kwargs):
  maintenance = ticket.maintenance
  # If a job is started but not completed, don't close the job out just yet. A
  # service provider may have just marked the final ticket as complete as
  # they're going about their business, but want the job to stay up on their
  # screens for a bit while they tidy up and hit Stop at an appropriate time.
  if maintenance and not maintenance.canceled_at and (
      not maintenance.started_at and not maintenance.completed_at):
    for other_ticket in maintenance.ticket_set.all():
      if other_ticket.sla != DONT_SCHEDULE and not other_ticket.completed_at:
        return
    maintenance.cancel(
        'All tickets in this job have sla DONT_SCHEDULE or are complete',
        api=kwargs.get('api', None))


def _schedule_emergency_immediately(ticket, **kwargs):
  """ The point of this is to try to schedule emergency tickets ASAP and not
  wait until the scheduler runs automatically every 10 minutes.

  There is a risk of an infinite loop here if the scheduler fails to either
  schedule or set the not_scheduled_reason. That's why
  _post_schedule_save_tickets throws an exception, even in prod, if there's an
  emergency ticket with neither. """
  is_emergency = ticket.sla == NOW
  yes_status = ticket.status() in [PRIORITIZED, DELAYED]
  no_reason_not = not ticket.not_scheduled_reason_id

  if is_emergency and yes_status and no_reason_not:
    next_checkout_days_in_advance = kwargs.get(
        'next_checkout_days_in_advance', 3)
    api = kwargs.get('api', None)
    nnow = kwargs.get('nnow', None)

    schedule_background(
        next_checkout_days_in_advance=next_checkout_days_in_advance, api=api,
        nnow=nnow)


@receiver(post_save, sender=Maintenance)
def maintenance_post_save_alert_incomplete(sender, instance, *args, **kwargs):
  if 'message_sender' in kwargs or settings.PROD:
    message_sender = kwargs.get('message_sender', MessageSender())
    if instance.status() == COMPLETE:
      if not Message.objects.filter(
          reason=DELAYED_TICKET, work=instance).exists():
        incomplete_tickets = []
        for ticket in instance.ticket_set.all():
          if ticket.status() == INCOMPLETE:
            incomplete_tickets.append(
                '{} {}'.format(ticket.title, ticket.keys_url()))
        if incomplete_tickets:
          content = (
              'These tickets are incomplete. Click the links for each ticket '
              'you wish to reschedule and click the "Reschedule" button. '
              '\n\n{}').format('\n'.join(incomplete_tickets))
          message_sender.send(Message.objects.create(
              to=instance.alerts_email(), reason=DELAYED_TICKET,
              kind=EMAIL, subject=DELAYED_TICKET, content=content,
              work=instance, when=now()))


def schedule(next_checkout_days_in_advance=3, api=None, nnow=None):
  """ This is the big fat function that schedules jobs to resolve tickets! If
  it can't schedule a ticket, it explains why. And it does all that without
  running a bazillion queries. """
  api = api or API()
  nnow = nnow or now()

  tickets = unscheduled_tickets()

  unaccepted_maintenances = list(get_upcoming_unaccepted_maintenances(nnow))
  updated_maintenances = set()
  first_pass_unscheduled_tickets = []
  # + 1 because I want to make sure I have enough data to say when the next
  # check_in is even if it's out of range, because that determines whether the
  # final valid day has a vacant night.
  nearby_reservations = Reservation.objects.reservations_in_range(
      nnow, nnow + timedelta(days=next_checkout_days_in_advance + 1))

  _set_reasons_right_off_the_bat_why_we_cant_schedule(tickets, nnow)

  for ticket in tickets:
    if ticket.not_scheduled_reason_id:
      continue
    added_to_maintenance = added_to_which_maintenance(
        ticket, unaccepted_maintenances)
    if added_to_maintenance:
      updated_maintenances.add(added_to_maintenance)
    elif _sla_or_mst_can_create_new_maintenance(ticket):
      timing_is_wrong = (
          _timing_explain_why_cant_start_new_maintenance(
              ticket, nearby_reservations, nnow,
              next_checkout_days_in_advance))
      if timing_is_wrong:
        ticket.not_scheduled_reason = timing_is_wrong
        first_pass_unscheduled_tickets.append(ticket)
      else:
        new_maintenance = _create_new_maintenance(
            ticket, next_checkout_days_in_advance, nearby_reservations,
            nnow)
        # Make sure remaining first pass tickets can see this new maintenance.
        # Otherwise a second NEXT_CHECKOUT would be, like, "Hey no suitable
        # maintenance to join. Better make my own."
        unaccepted_maintenances.append(new_maintenance)
        updated_maintenances.add(new_maintenance)
    else:
      first_pass_unscheduled_tickets.append(ticket)

  for ticket in first_pass_unscheduled_tickets:
    added_to_maintenance = added_to_which_maintenance(
        ticket, unaccepted_maintenances)
    if added_to_maintenance:
      ticket.not_scheduled_reason = None
      updated_maintenances.add(added_to_maintenance)
    elif not _sla_or_mst_can_create_new_maintenance(ticket):
      ticket.not_scheduled_reason = not_scheduled_reason_finder.by_name(
          'There aren\'t any unaccepted, upcoming Maintenance jobs with an '
          'appropriate SLA for this rental that I can attach this to')

  _post_schedule_save_tickets(tickets, nnow)


def _create_new_maintenance(
    ticket, next_checkout_days_in_advance, reservations, nnow):
  offered_start_time = _get_offered_start_time(
      ticket, next_checkout_days_in_advance, reservations, nnow)
  if offered_start_time.tzinfo == UTC:
    raise Exception('I expect offered_start_time to be local time.')
  deadline = None
  fixed_or_flexible = FLEXIBLE
  if ticket.manual_start_time:
    fixed_or_flexible = FIXED
  elif ticket.sla == NOW:
    deadline = offered_start_time + timedelta(hours=4)
  elif ticket.sla == URGENT:
    deadline = offered_start_time + timedelta(hours=24)
  elif ticket.sla == NEXT_CHECKOUT:
    # These .replace calls replace in the timezone of offered_start_time.
    deadline = offered_start_time.replace(
        hour=15, minute=45, second=0, microsecond=0)
  elif ticket.sla == NEXT_VACANT_NIGHT:
    deadline = offered_start_time.replace(
        hour=23, minute=55, second=0, microsecond=0)
  else:
    raise Exception(ticket.sla)
  maintenance = Maintenance.objects.create(
      offered_start_time=offered_start_time,
      fixed_or_flexible=fixed_or_flexible,
      deadline=deadline)
  ticket.maintenance = maintenance
  ticket.save()
  maintenance.set_offered_to()
  # Now that maintenance is totally removed from Properly, the creation is
  # confirmed as soon as we create it. This is important for def status
  maintenance.creation_confirmed = nnow
  maintenance.save()
  return maintenance


def _get_offered_start_time(
    ticket, next_checkout_days_in_advance, reservations, nnow):
  """ This function is closely related to
  _timing_explain_why_cant_start_new_maintenance. """
  if ticket.manual_start_time:
    return ticket.rental.building.set_timezone(ticket.manual_start_time)
  elif ticket.sla in [NOW, URGENT]:
    return nnow + timedelta(minutes=5)
  elif ticket.sla in [NEXT_CHECKOUT, NEXT_VACANT_NIGHT]:
    got_maintenance_windows = maintenance_windows(
        ticket.rental, next_checkout_days_in_advance,
        reservations=reservations, nnow=nnow)
    if ticket.vacant_night_required():
      got_maintenance_windows = _vacant_nights_only(got_maintenance_windows)
    if not ticket.rental.maintenance_purposes_only:
      if ticket.vacant_night_required():
        got_maintenance_windows = _weeknights_only(got_maintenance_windows)
      got_maintenance_windows = _before_or_after_reservation_only(
          got_maintenance_windows, ticket.vacant_night_required())
    if not len(got_maintenance_windows):
      raise Exception((
          'Why are you calling _get_offered_start_time on ticket {} '
          'at {} when there arent any valid days to schedule it on?').format(
              ticket.keys_url(), tz_dt_to_str(nnow)))
    return got_maintenance_windows[0].start_at
  else:
    raise Exception('{} {}'.format(ticket.pk, ticket.sla))


def _set_reasons_right_off_the_bat_why_we_cant_schedule(tickets, nnow):
  for ticket in tickets:
    ticket.not_scheduled_reason = _non_context_explain_why_cant_schedule(
        ticket, nnow)
  _set_worker_explain_why_cant_schedule(tickets)


def _post_schedule_save_tickets(tickets, nnow):
  for ticket in tickets:
    if not (ticket.not_scheduled_reason or ticket.maintenance):
      message = (
          '{}\n\nI attempted to schedule this ticket but it has neither a '
          'not_scheduled_reason nor a maintenance.').format(
              ticket.keys_url())
      if ticket.sla == NOW or not settings.PROD:
        # There's a danger of an infinite loop in ticket_post_save if any
        # emergency tickets leave this function with neither a maintenance nor
        # a reason why it wasn't scheduled.
        raise Exception(message)
      else:
        log_error('A ticket wasnt scheduled but I dont know why', message)
    ticket.last_attempt_to_schedule = nnow
    # Here's where ticket_post_save triggers. This should come after the bit
    # that raises an exception if something weird happens.
    ticket.save()


def _timing_explain_why_cant_start_new_maintenance(
    ticket, reservations, nnow, next_checkout_days_in_advance):
  """ This function is closely related to _get_offered_start_time. """
  if not _sla_or_mst_can_create_new_maintenance(ticket):
    raise Exception((
        'Why are you asking about starting a new maintenance on a ticket with '
        'sla {}?').format(ticket.sla))
  if ticket.sla == NOW:
    return  # NOW gets scheduled immediately.
  elif ticket.sla == URGENT:
    if ticket.created_at + timedelta(minutes=30) > nnow:
      return not_scheduled_reason_finder.by_name(
          'URGENT tickets wait 30 minutes before creating a job')
  elif ticket.manual_start_time:
    if ticket.created_at + timedelta(minutes=10) > nnow:
      return not_scheduled_reason_finder.by_name(
          'Tickets with manual start times wait 10 minutes to schedule')
  elif ticket.sla in [NEXT_CHECKOUT, NEXT_VACANT_NIGHT]:
    got_maintenance_windows = maintenance_windows(
        ticket.rental, next_checkout_days_in_advance,
        reservations=reservations, nnow=nnow)
    if not got_maintenance_windows:
      return not_scheduled_reason_finder.by_name(
          'The next {} days are taken up by a single reservation'.format(
              next_checkout_days_in_advance))

    if ticket.vacant_night_required():
      got_maintenance_windows = _vacant_nights_only(got_maintenance_windows)
      if not got_maintenance_windows:
        return not_scheduled_reason_finder.by_name(
            'There are no vacant nights in the next {} days'.format(
                next_checkout_days_in_advance))

    if not ticket.rental.maintenance_purposes_only:
      if ticket.vacant_night_required():
        got_maintenance_windows = _weeknights_only(got_maintenance_windows)
        if not got_maintenance_windows:
          return not_scheduled_reason_finder.by_name(
              'The only vacant nights are on weekends which are too valuable '
              'to block for maintenance')
        got_maintenance_windows = _before_or_after_reservation_only(
            got_maintenance_windows, ticket.vacant_night_required())
        if not got_maintenance_windows:
          return not_scheduled_reason_finder.by_name(
              'There aren\'t any non-weekend vacant nights before or after a '
              'reservation')
      else:
        got_maintenance_windows = _before_or_after_reservation_only(
            got_maintenance_windows, ticket.vacant_night_required())
        if not got_maintenance_windows:
          return not_scheduled_reason_finder.by_name(
              'There aren\'t any check ins or outs in the next {} days'.format(
                  next_checkout_days_in_advance))

    next_usable_checkout = got_maintenance_windows[0].start_at
    if nnow > next_usable_checkout:
      raise Exception(
          'You can\'t schedule in the past. {} > {} for ticket {}.'.format(
              nnow, next_usable_checkout, ticket.pk))

    if next_usable_checkout <= nnow + timedelta(hours=3):
      return  # Schedule immediately.

    if ticket.created_at + timedelta(hours=12) > nnow:
      return not_scheduled_reason_finder.by_name((
          '{} tickets wait 12 hours, or until 3 hours before the next usable '
          'time before creating a job').format(ticket.sla))
  else:
    raise Exception(ticket.sla)


def _vacant_nights_only(maintenance_windows):
  return [day for day in maintenance_windows if day.is_vacant_night()]


def _weeknights_only(maintenance_windows):
  to_return = []
  for maintenance_window in maintenance_windows:
    day = maintenance_window.start_at.date()
    if calendar.weekday(day.year, day.month, day.day) not in (4, 5):
      to_return.append(maintenance_window)
  return to_return


def _before_or_after_reservation_only(
    maintenance_windows, vacant_night_required):
  to_return = []
  for maintenance_window in maintenance_windows:
    if vacant_night_required:
      if maintenance_window.vacant_night_before_or_after_reservation():
        to_return.append(maintenance_window)
    else:
      if maintenance_window.before_or_after_reservation():
        to_return.append(maintenance_window)
  return to_return


def _sla_or_mst_can_create_new_maintenance(ticket):
  return ticket.manual_start_time or ticket.sla in [
      NOW, URGENT, NEXT_CHECKOUT, NEXT_VACANT_NIGHT]


def _non_context_explain_why_cant_schedule(ticket, nnow):
  """ This is for reasons you can't schedule a ticket that don't involve the
  context of other tickets and Maintenance instances, a.k.a., pretty
  straightforward reasons. """
  if ticket.not_our_responsibility:
    return not_scheduled_reason_finder.by_name(
        'It\'s not our responsibility to resolve this ticket')
  if not ticket.sla and not ticket.manual_start_time:
    return not_scheduled_reason_finder.by_name(THIS_TICKET_LACKS_SLA)
  if ticket.sla == DONT_SCHEDULE:
    return not_scheduled_reason_finder.by_name(
        'No need to schedule a ticket we won\'t fix.')
  if int(bool(ticket.work_type)) + int(ticket.offered_to.exists()) != 1:
    if bool(ticket.work_type):
      return not_scheduled_reason_finder.by_name(
          'You can\'t specify both work_type and offered_to')
    else:
      return not_scheduled_reason_finder.by_name(
          'You must specify precisely 1 of work_type and offered_to')
  if int(bool(ticket.checklist)) + int(
      bool(ticket.existing_checklist_url)) != 1:
    return not_scheduled_reason_finder.by_name(
        'You must set either the checklist or the existing_checklist_url')
  if ticket.existing_checklist_url and not get_checklist_id_from_url(
      ticket.existing_checklist_url):
    return not_scheduled_reason_finder.by_name(
        'The existing checklist url is invalid')
  if not ticket.rental.properlyrental_or_none:
    return not_scheduled_reason_finder.by_name(
        'This rental isn\'t configured with a Properly Rental')
  if not ticket.rental.properlyrental.is_configured():
    return not_scheduled_reason_finder.by_name(
        'This rental\'s Properly Rental ID isn\'t set')


def _set_worker_explain_why_cant_schedule(tickets):
  """ This checks if any workers are configured for both the ticket and the
  rental. """
  ticket_ids = ','.join([str(ticket.pk) for ticket in tickets])
  ticket_worker_lookup = {}
  if ticket_ids:
    query = """
        SELECT ticket_id, worker_id
        FROM work_ticket_offered_to
        WHERE ticket_id IN ({});""".format(ticket_ids)
    for ticket, worker in get_pairs(query, Ticket, IndependentWorker):
      if ticket not in ticket_worker_lookup:
        ticket_worker_lookup[ticket] = set()
      ticket_worker_lookup[ticket].add(worker)

  building_work_type_lookup = (
      IndependentWorker.objects.get_building_work_type_lookup())
  building_worker_lookup = (
      IndependentWorker.objects.get_building_worker_lookup())
  for ticket in tickets:
    if ticket.not_scheduled_reason_id:
      continue
    if ticket.work_type:
      if ticket.work_type not in building_work_type_lookup.get(
          ticket.rental.building, set()):
        ticket.not_scheduled_reason = not_scheduled_reason_finder.by_name(
            'There are no workers of this type configured for '
            'this building')
    else:
      ticket_workers = ticket_worker_lookup.get(ticket, set())
      building_workers = building_worker_lookup.get(
          ticket.rental.building, set())
      if not ticket_workers & building_workers:
        ticket.not_scheduled_reason = not_scheduled_reason_finder.by_name(
            'None of the workers configured for this ticket are '
            'configured for this building')


def get_upcoming_unaccepted_maintenances(nnow):
  # You can't necessarily count on accepted_by being there. Properly may have
  # failed to send a webhook. That's why I also check started_at and
  # completed_at.
  return Maintenance.objects.filter(
      ~Q(job_request_id=''), accepted_by__isnull=True,
      canceled_at__isnull=True,
      started_at__isnull=True, completed_at__isnull=True,
      offered_start_time__gt=nnow)


def unscheduled_tickets():
  """ For URGENT and NOW, don't automatically reschedule because you can end up
  in a reschedule, cancel loop, and anyway it's a dicey situation that
  probably needs somebody to look at it. Other SLAs though, canceled
  counts as no maintenance. """
  null_or_canceled_maintenance = Q(maintenance__isnull=True) | Q(
      maintenance__canceled_at__isnull=False)
  non_urgent = ~Q(sla__in=[NOW, URGENT])
  non_urgent_and_non_maintenance = null_or_canceled_maintenance & non_urgent

  urgent_and_no_maintenance = Q(
      sla__in=[NOW, URGENT], maintenance__isnull=True)
  return Ticket.objects.filter(
      non_urgent_and_non_maintenance | urgent_and_no_maintenance,
      completed_at__isnull=True).order_by('pk')


def added_to_which_maintenance(ticket, unaccepted_maintenances):
  for maintenance in unaccepted_maintenances:
    if _can_add_to_maintenance(ticket, maintenance):
      ticket.maintenance = maintenance
      ticket.save()
      return maintenance


def _can_add_to_maintenance(ticket, maintenance):
  for scheduled_ticket in maintenance.ticket_set.all():
    if not compatible(ticket, scheduled_ticket):
      return False
  return True


def compatible(ticket1, ticket2):
  def _sla_category(ticket):
    sla = ticket.sla
    if sla in [NOW, URGENT]:
      return URGENT
    elif sla in [NEXT_CHECKOUT, NEXT_VACANT_NIGHT, NEXT_VISIT]:
      return NEXT_VISIT
    elif ticket.manual_start_time:
      return ticket.manual_start_time
    elif sla == DONT_SCHEDULE:
      raise Exception(
          'Why are you asking about the sla category of a DONT_SCHEDULE '
          'ticket?')
    raise Exception(sla)
  return all([
      ticket1.rental == ticket2.rental,
      _sla_category(ticket1) == _sla_category(ticket2),
      ticket1.work_type == ticket2.work_type,
      set(ticket1.offered_to.all()) == set(ticket2.offered_to.all())])


@background_command
def double_check_blocks_background(
    nnow=None, scheduling_api=None, error_logger=None):
  nnow = nnow or now()
  error_logger = error_logger or ErrorLogger

  maintenances = Maintenance.objects.filter(
      ticket__sla=NEXT_VACANT_NIGHT, offered_start_time__gte=nnow).distinct()

  availability_lookup = {}  # (rental, date) -> availability
  should_block = {}  # rental -> set(dates)

  MRB = namedtuple(
      'MRB',
      'maintenance rental block_date accepted canceled blocked')
  mrbs = []
  for maintenance in maintenances:
    accepted = maintenance.status() == ACCEPTED
    canceled = maintenance.status() == CANCELED

    if accepted or canceled:
      rental = maintenance.get_rental()
      block_date = maintenance.offered_start_time.date()
      key = (rental, block_date)
      if key not in availability_lookup:
        # The alternatives to UNAVAILABLE are [AVAILABLE, BOOKED], fyi.
        blocked = rental.get_availability(
            block_date, api=scheduling_api) == UNAVAILABLE
        availability_lookup[key] = blocked
      mrb = MRB(
          maintenance, rental, block_date, accepted, canceled,
          availability_lookup[key])
      mrbs.append(mrb)

      if rental not in should_block:
        should_block[rental] = set()
      if accepted:
        should_block[rental].add(block_date)

  # Gotta do 2 passes because if any vacant night maintenances are still
  # active, then the date should be blocked.
  for mrb in mrbs:
    if mrb.accepted and not mrb.blocked:
      error_logger.log_error(
          'Maintenance failed to block', mrb.maintenance.keys_url())
    elif mrb.canceled and mrb.blocked and (
        mrb.block_date not in should_block[mrb.rental]):
      error_logger.log_error(
          'Canceled maintenance failed to unblock',
          mrb.maintenance.keys_url())
