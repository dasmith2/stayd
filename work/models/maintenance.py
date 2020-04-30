from django.db import models
from django.db.models import Q
from django.dispatch import receiver
from django.shortcuts import reverse

from commands.models import background_command
from errors.models import log_error
from rentals.models import Rental
from reservations.models import Reservation
from util.signals import post_sync
from util.timezone import now
from work.models.fixed_or_flexible import FLEXIBLE
from work.models.message import Message, HIGH_PRIORITY_TICKET_JOB_CANCELED
from work.models.rental import ProperlyRental
from work.models.sla import NOW, URGENT
from work.models.work import Work
from work.models.worker import IndependentWorker


def busy(worker, nnow=None):
  nnow = nnow or now()
  return Maintenance.objects.filter(
      accepted_by=worker, offered_start_time__date=nnow.date(),
      started_at__isnull=False, completed_at__isnull=True,
      canceled_at__isnull=True).exists()


@background_command
def clean_up_empty_maintenance_background(nnow=None):
  clean_up_empty_maintenance(nnow=nnow)


def clean_up_empty_maintenance(nnow=None):
  """ Tickets reassign themselves to jobs all the time. This causes abandoned
  maintenance jobs. """
  nnow = nnow or now()
  for maintenance in Maintenance.objects.filter(
      ticket__isnull=True, offered_start_time__lt=nnow,
      started_at__isnull=True, completed_at__isnull=True):
    if not maintenance.canceled_at:
      maintenance.cancel('Abandoned')
    maintenance.delete()


@receiver(post_sync, sender=Reservation)
def post_reservation_sync(sender, instance, *args, **kwargs):
  api = kwargs.get('api', None)
  if instance.confirmed():
    for rental in instance.rental.get_rentals():
      # You need distinct otherwise this returns each maintenance once per
      # matching ticket. You'd expect some NOW and URGENT maintenances to
      # overlap with reservations.
      maintenances = Maintenance.objects.filter(
          ~Q(ticket__sla__in=[NOW, URGENT]),
          ticket__manual_start_time__isnull=True, ticket__rental=rental,
          canceled_at__isnull=True, completed_at__isnull=True,
          offered_start_time__gte=instance.check_in,
          offered_start_time__lte=instance.check_out).distinct()
      for maintenance in maintenances:
        if maintenance.started_at:
          subject = (
              'A reservation was just booked over top of a maintenance that '
              'started already')
          content = '{}\n{}'.format(
              instance.keys_url(), maintenance.keys_url())
          log_error(subject, content)
        else:
          if maintenance.accepted_by:
            reason = 'A reservation booked over top of this job'
          else:
            reason = 'A guest booked a stay before this job was accepted'
          maintenance.cancel(reason, api=api)


class Maintenance(Work):
  """ A Maintenance is a Work that can handle more than one checklist. The
  point of a Maintenance is to resolve one or more tickets, which happens when
  a service provider checks off all the tasks in the corresponding checklist.
  Recall that each ticket has one checklist.

  In order for multiple tickets to be in the same maintenance, they should have
  the same rental and offered to. """
  rental = models.ForeignKey(
      Rental, on_delete=models.PROTECT, null=True, blank=True, help_text=(
          'This is set automatically in ticket_scheduler when a ticket is '
          'added to this job.'))
  title = models.CharField(max_length=300, default='', blank=True, help_text=(
      'This is set automatically in ticket_scheduler when a ticket is added '
      'to this job.'))

  def invoice_prefix(self):
    return 'hm'

  def in_properly(self):
    # Yaaay!
    return False

  def get_rental(self):
    return self.rental

  def reschedule(self, *args, **kwargs):
    # The ticket scheduler will see that this job is canceled and will
    # reschedule all the tickets appropriately.
    pass

  def url(self):
    return reverse('maintenance_history_detail', kwargs={'pk': self.pk})

  def get_expected_duration(self):
    # This is kind of the ideal
    sum_expected = sum(
        [ticket.expected_duration for ticket in self.ticket_set.all()])
    # Tickets with manual start times create FIXED maintenance so there's no
    # deadline.
    if not self.deadline:
      return sum_expected
    # But for flexible jobs the actual maintenance window may be shorter than
    # the sum of the expected durations of the tickets. Properly won't create a
    # job if you say the expected duration is longer than the time allotted to
    # do the job.
    return min(sum_expected, self.deadline_minus_start_time_hours())

  def get_title(self):
    tickets = self.ticket_set.all()
    if len(tickets) == 0:
      return self.title
    if len(tickets) == 1:
      return tickets[0].title
    return '{} tickets: {}'.format(
        len(tickets), ', '.join([ticket.short_title() for ticket in tickets]))

  def get_readable_work_title(self):
    return self.get_title()

  def troubling_creation_attempt_count(self):
    return 20

  def get_deadline(self):
    return self.deadline

  def alert_unaccepted_late_start(self):
    return False

  def get_source_property_id(self):
    rental = self.get_rental()
    properly_rental = ProperlyRental.objects.filter(rental=rental).first()
    if not properly_rental:
      raise Exception('{} needs a properly rental'.format(rental.nickname))
    return properly_rental.get_source_property_id()

  def get_properly_checklist_ids(self, api=None):
    tickets = self.ticket_set.order_by('pk')
    return [ticket.get_checklist_id(api=api) for ticket in tickets]

  def checklist_complete_on_properly(self, who_completed_it, checklist_id):
    # On Properly, you can't mark a ticket complete exactly. But you can mark
    # each item of the checklist complete, in which case we consider this
    # ticket complete.
    if len(checklist_id) < 5:
      # If somebody passes, like, checklist_id = '1', it's very likely to match
      # the existing_checklist_url.
      raise Exception(
          '{} doesn\'t seem to be a valid checklist_id'.format(checklist_id))
    ticket = self.ticket_set.filter(
        Q(checklist__checklist_id=checklist_id) | Q(
            existing_checklist_url__contains=checklist_id)).first()
    if ticket:
      ticket.mark_completed('{} on Properly'.format(who_completed_it))

  def get_message(self):
    return '\n'.join(filter(None, [
        ticket.appendix for ticket in self.ticket_set.order_by('pk')]))

  def should_offer_to(self):
    ticket = self.ticket_set.first()
    return IndependentWorker.objects.should_offer_to(
        ticket.work_type, ticket.offered_to.all(),
        ticket.rental.building, FLEXIBLE,
        self.offered_start_time, self.get_expected_duration())

  def explain_why_cant_add_ticket(self, ticket):
    if self.job_request_id:
      return 'This job was sent out already.'

  def check_consistent_tickets(self):
    tickets = self.ticket_set.all()
    first = tickets[0]
    for ticket in tickets[1:]:
      if first.explain_why_not_consistent(ticket):
        log_error()

  def vacant_night_required(self):
    ticket = self.ticket_set.first()
    if ticket:
      return ticket.vacant_night_required()

  def was_canceled(
      self, permanently_canceled_reason, api=None, message_sender=None,
      scheduling_api=None, **kwargs):
    """ Blocking happens in set_accepted_by, unblocking in was_canceled. One
    time I wrote a bug that re-canceled, hence the dupe checks here. """
    super().was_canceled(
        permanently_canceled_reason, api=api, message_sender=message_sender,
        **kwargs)
    if Message.objects.filter(
        reason=HIGH_PRIORITY_TICKET_JOB_CANCELED, work=self).exists():
      return
    if self.ticket_set.filter(
        sla__in=[URGENT, NOW], completed_at__isnull=True).exists():
      content = (
          'This job contains high priority tickets: {}\n\nHowever, '
          'the job was canceled. These tickets will NOT be automatically '
          'rescheduled. You probably want to\n\n1. Reassign the tickets '
          'to a service provider who won\'t cancel\n2. Click the Reschedule '
          'button.\n\n{}').format(self.keys_url(), '\n'.join(
              [ticket.keys_url() for ticket in self.ticket_set.all()]))
      Message.objects.create_and_send_email(
          self.alerts_email(), HIGH_PRIORITY_TICKET_JOB_CANCELED, content,
          self, message_sender=message_sender)
    if self.vacant_night_required() and self.accepted_by:
      self.get_rental().unblock(self.offered_start_time.date(), scheduling_api)

  def set_accepted_by(self, worker, scheduling_api=None):
    """ Blocking happens in set_accepted_by, unblocking in was_canceled. """
    super().set_accepted_by(worker)
    if self.vacant_night_required():
      self.get_rental().block(
          self.offered_start_time.date(),
          'Vacant night required for maintenance', scheduling_api)

  def high_priority(self):
    return any([
        ticket.is_high_priority() for ticket in self.ticket_set.all()])
