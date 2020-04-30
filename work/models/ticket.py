""" A Ticket is a description of a problem including how important it is and
where it is. Tickets get added to Maintenance jobs so somebody can actually
resolve them.

work.models.ticket_scheduler is a whole thing. Some stuff that would kind of
make sense here, such as "Explain why I cant schedule this ticket" is located
there.  """
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.shortcuts import reverse

from commands.models import background_command
from photos.models import Photo
from rentals.models import Rental
from work.models.maintenance_checklist import (
    MaintenanceChecklist, get_checklist_id_from_url)
from work.models.maintenance import Maintenance
from work.models.message import (
    Message, MessageSender, INFORM_OF_TICKET_COUNT_NO_SLA, EMAIL)
from work.models.not_scheduled_reason import (
    NotScheduledReason, not_scheduled_reason_finder)
from work.models.sla import (
    SLA_CHOICES, NEXT_VACANT_NIGHT, DONT_SCHEDULE, NOW, URGENT)
from work.models.work import (
    Work,
    CREATING, OFFERED, ACCEPTED, STARTED, COMPLETE, CANCELED, CREATION_ERROR)
from work.models.worker import Worker
from work.models.work_co_worker import WorkCoWorker
from work.models.work_type import WorkType
from util.fields import OneToOneOrNoneField
from util.timezone import now
from util.urls import date_to_url_str, keys_url


# Statuses
NEW = 'New'
PRIORITIZED = 'Prioritized'
DELAYED = 'Delayed'
NOT_OUR_RESPONSIBILITY = 'Not our responsibility'
INCOMPLETE = 'Incomplete'
NOPE = 'Nope'


STATUSES = [
    NEW, PRIORITIZED, CREATING, OFFERED, ACCEPTED, STARTED, COMPLETE,
    DELAYED, NOT_OUR_RESPONSIBILITY, INCOMPLETE]


THIS_TICKET_LACKS_SLA = 'This ticket doesn\'t have an SLA or manual start time'


@background_command
def email_no_sla_ticket_count_background():
  email_no_sla_ticket_count()


def email_no_sla_ticket_count(message_sender=None):
  """ Tell Tom how many tickets still need to be looked at. """
  message_sender = message_sender or MessageSender()
  not_scheduled_reason = not_scheduled_reason_finder.by_name(
      THIS_TICKET_LACKS_SLA)
  min_created = None
  max_created = None
  how_many = 0
  for ticket in Ticket.objects.filter(
      not_scheduled_reason=not_scheduled_reason, completed_at__isnull=True):
    how_many += 1
    if not min_created or ticket.created_at < min_created:
      min_created = ticket.created_at
    if not max_created or ticket.created_at > max_created:
      max_created = ticket.created_at

  if how_many:
    to = max_created.date() + timedelta(days=1)
    url_path = reverse(
        'tickets', kwargs={
            'from_date_str': date_to_url_str(min_created.date()),
            'to_date_str': date_to_url_str(to)})
    subject = 'Please look at {} because they lack an SLA'
    if how_many == 1:
      subject = subject.format('this 1 ticket')
    else:
      subject = subject.format('these {} tickets'.format(how_many))
    content = (
        'These tickets need an SLA before we can fix them:\n\n'
        '{}?not_scheduled_reason_id={}').format(
            keys_url(url_path), not_scheduled_reason.pk)
    message_sender.send(Message.objects.create(
        to=settings.EMAIL_TWICE_DAILY_SLA_LESS_TICKET_COUNT,
        reason=INFORM_OF_TICKET_COUNT_NO_SLA, kind=EMAIL,
        subject=subject, content=content, when=now()))


class TicketManager(models.Manager):
  def create_from_properly_reported_problem(self, raw_event):
    if not raw_event.work:
      return
    rental = raw_event.work.get_child_class_instance().get_rental()
    if not rental:
      return

    data = raw_event.data()

    for problem in data['results'][0]['problems']:
      email = problem['serviceProvider']['email']
      service_provider = Worker.objects.filter(email=email).first()
      if service_provider:
        service_provider = service_provider.get_child_class_instance()
      if not self.filter(external_id=problem['problemId']).exists():
        notes = ''
        image_url = ''
        if len(problem['pictures']):
          image_url = problem['pictures'][0]
        if service_provider:
          notes = 'Reported by {} {}'.format(
              service_provider.name, service_provider.email)
          if isinstance(service_provider, WorkCoWorker):
            notes += ' who works for {}'.format(service_provider.work_co.name)
        actual_title = problem.get('note', '')
        if actual_title or image_url:
          title = (actual_title or '(No words, just a picture)').strip()[:300]
          self.create(
              external_id=problem['problemId'],
              title=title, rental=rental, internal_notes=notes,
              came_from=PROPERLY, image_url=image_url,
              reported_by=service_provider)


PROPERLY = 'Properly'
TICKETS_PAGE = 'Tickets page'
REGULAR_MAINTENANCE = 'Regularly scheduled maintenance'
WORK_NEW_TICKET = 'work.hihoward.com new ticket'
WORK_START_TICKET = 'work.hihoward.com start new ticket'
CLEAN_HIHOWARD_COM = 'clean.hihoward.com report problem'
CAME_FROMS = [
    PROPERLY, TICKETS_PAGE, REGULAR_MAINTENANCE, WORK_NEW_TICKET,
    WORK_START_TICKET, CLEAN_HIHOWARD_COM]
CAME_FROM_CHOICES = [
    (came_from, came_from) for came_from in CAME_FROMS]


class Ticket(models.Model):
  """ A Ticket wants to be resolved. It gets added to a Maintenance, which is
  the actual job that gets sent out. """
  title = models.CharField(
      max_length=300, help_text='What seems to be the problem?')
  rental = models.ForeignKey(Rental, on_delete=models.PROTECT, help_text=(
      'Where\'s the problem?'))

  sla = models.CharField(
      default='', blank=True, max_length=100, choices=SLA_CHOICES, help_text=(
          'How urgent is this ticket? In other words, how fast must it be '
          'resolved? If all the tickets in a Maintenance Job get sla '
          '"Don\'t schedule", I\'ll automatically cancel the job.'))
  manual_start_time = models.DateTimeField(
      null=True, blank=True, help_text=(
          'Instead of an SLA, you can specify an exact time you want this '
          'ticket scheduled.'))

  expected_duration = models.DecimalField(
      decimal_places=2, max_digits=5, default=1,
      help_text='How long do we expect this job to take in hours?')

  checklist = models.ForeignKey(
      MaintenanceChecklist, on_delete=models.PROTECT, null=True, blank=True,
      help_text=(
          'What steps are necessary to solve the problem?'))
  existing_checklist_url = models.CharField(
      max_length=200, default='', blank=True, help_text=(
          'WARNING: This doesn\'t work on the keys maintenance page!'))

  came_from = models.CharField(
      max_length=100, choices=CAME_FROM_CHOICES,
      help_text='What stream of information birthed this ticket?')
  external_id = models.CharField(
      max_length=100, default='', blank=True, help_text=(
          'If a complaint comes in with an ID of some sort, put that here so '
          'we can avoid duplicates.'))
  came_from_work = models.ForeignKey(
      Work, on_delete=models.CASCADE, null=True, blank=True,
      related_name='created_ticket_set', help_text=(
          'Your doing a cleaning. You report an issue. You see a list of '
          'issues you reported during your cleaning.'))
  # This is a string because, for the time being, we get strings from Properly.
  image_url = models.CharField(
      max_length=300, default='', blank=True, help_text=(
          'An url pointing to an image showing the problem'))
  internal_notes = models.TextField(
      default='', blank=True,
      help_text=(
          'These notes are only visible here. The service provider will not '
          'see them.'))
  reported_by = models.ForeignKey(
      Worker, null=True, blank=True, on_delete=models.PROTECT)
  appendix = models.TextField(
      default='', blank=True,
      help_text=(
          'The service provider will see this. Use it for style '
          'guides, references, and other links. Don\'t duplicate the '
          'title or checklist here.'))

  # Who should do the work
  work_type = models.ForeignKey(
      WorkType, blank=True, null=True, on_delete=models.PROTECT, help_text=(
          'WARNING: The point of this field is to overwrite "Offered to"'))
  offered_to = models.ManyToManyField(
      Worker, related_name='ticket_offered_to', blank=True, help_text=(
          'If you didn\'t specify a work_type, who would you like to offer '
          'this ticket to specifically?'))
  not_our_responsibility = models.TextField(default='', blank=True, help_text=(
      'If it\'s somebody else\'s job to fix this, such as the owner or '
      'property manager, describe that here and I won\'t add this ticket to '
      'a maintenance job.'))

  # Scheduling
  maintenance = models.ForeignKey(
      Maintenance, on_delete=models.PROTECT, null=True, blank=True, help_text=(
          'What maintenance job will resolve this ticket?'))
  created_at = models.DateTimeField(auto_now_add=True, db_index=True)
  completed_at = models.DateTimeField(null=True, blank=True, help_text=(
      'This is set automatically if all the items in the checklist get '
      'checked off. You can also set it manually. Note: simply completing '
      'the Maintenance job will NOT mark this ticket as complete!'))
  not_completed_at = models.DateTimeField(null=True, blank=True, help_text=(
      'When, if ever, did the service provider explicitly says they were '
      'unable to complete the ticket?'))
  # For debugging purposes. Right now I got a few examples of jobs that don't
  # have action_on_(anywhere) or a started_at, but then all the tickets were
  # marked resolved, and the job was canceled, and people freaked out about
  # that.
  completed_by_description = models.TextField(
      default='', blank=True, help_text=(
          'An explanation of who completed the ticket and where.'))
  last_attempt_to_schedule = models.DateTimeField(
      null=True, blank=True, help_text=(
          'When did the software last look at this ticket and attempt to '
          'schedule it?'))
  not_scheduled_reason = models.ForeignKey(
      NotScheduledReason, on_delete=models.PROTECT, null=True,
      blank=True, help_text=(
          'The last time we tried to schedule this ticket but couldn\'t, why '
          'was that?'))

  objects = TicketManager()

  def __repr__(self):
    return '<Ticket {}: {}>'.format(self.pk, self.title[:30])

  def mark_completed(self, completed_by_description, nnow=None):
    self.completed_at = nnow or now()
    self.not_completed_at = None
    self.not_scheduled_reason = None
    self.save()

  def mark_incomplete(self, nnow=None):
    self.completed_at = None
    self.not_completed_at = nnow or now()
    self.not_scheduled_reason = None
    self.save()

  def url(self):
    return reverse('ticket', kwargs={'pk': self.pk})

  def keys_url(self):
    return keys_url(self.url())

  def vacant_night_required(self):
    return self.sla == NEXT_VACANT_NIGHT

  def clean(self):
    super().clean()
    if self.rental.is_combo_rental():
      raise ValidationError(
          'Tickets should be filed against individual rentals, not combo '
          'rentals like {}.'.format(self.rental.nickname))
    if self.manual_start_time and self.sla not in ['', None, DONT_SCHEDULE]:
      raise ValidationError(
          'Tickets with a manual start time can\'t have SLA {}.'.format(
              self.sla))
    if self.completed_at and not self.completed_by_description:
      raise ValidationError(
          'Please explain who completed this ticket and where they completed '
          'it in the completed_by_description field.')

  def duplicate(self):
    ticket = Ticket.objects.create(
        title=self.title,
        rental=self.rental,
        sla='',
        expected_duration=self.expected_duration,
        checklist=self.checklist,
        existing_checklist_url=self.existing_checklist_url,
        internal_notes=self.internal_notes,
        appendix=self.appendix,
        work_type=self.work_type,
        not_our_responsibility=self.not_our_responsibility)
    ticket.offered_to.set(self.offered_to.all())
    return ticket

  def is_high_priority(self):
    return self.sla in [NOW, URGENT]

  def status(self, nnow=None):
    nnow = nnow or now()
    if self.completed_at:
      return COMPLETE
    if self.not_our_responsibility:
      return NOT_OUR_RESPONSIBILITY
    if self.sla == DONT_SCHEDULE:
      return NOPE
    if self.sla == NOW and nnow - self.created_at >= timedelta(hours=4):
      return DELAYED
    if self.sla == URGENT and nnow - self.created_at >= timedelta(hours=24):
      return DELAYED
    if self.maintenance and self.maintenance.status() not in [
        CANCELED, CREATION_ERROR]:
      if self.maintenance.status() in [CREATING, OFFERED, ACCEPTED, STARTED]:
        return self.maintenance.status()
      elif self.maintenance.status() == COMPLETE:
        return INCOMPLETE
    if all([
        self.sla,
        self.checklist or self.existing_checklist_url,
        self.work_type or self.offered_to.exists()]):
      return PRIORITIZED
    return NEW

  def can_chuck_photos(self):
    return self.status() in [COMPLETE, NOT_OUR_RESPONSIBILITY, NOPE]

  def get_checklist_id(self, api=None):
    if self.checklist:
      if not self.checklist.checklist_id:
        self.checklist.create_checklist(api)
      return self.checklist.checklist_id
    return get_checklist_id_from_url(self.existing_checklist_url)

  def can_edit_anything(self):
    return not self.completed_at

  def can_edit_everything(self):
    return self.can_edit_anything() and (
        (not self.maintenance) or self.maintenance.can_edit() or (
            self.maintenance.canceled_at or self.maintenance.completed_at))

  def short_title(self):
    if len(self.title) <= 20:
      return self.title
    return self.title[:17] + '...'


class TicketPhoto(Photo):
  """ Originally we got photos simply as strings from Properly. But now we're
  building our own thing and collecting our own photos. """
  ticket = OneToOneOrNoneField(Ticket, on_delete=models.CASCADE)

  def save(self, *args, **kwargs):
    super().save(*args, **kwargs)
    if self.ticket.image_url != self.url():
      self.ticket.image_url = self.url()
      self.ticket.save()

  def delete(self, s3=None):
    if self.ticket.image_url == self.url():
      self.ticket.image_url = ''
      self.ticket.save()
    super().delete(s3=s3)

  def explain_why_no_need_for_photo(self, nnow=None):
    if self.ticket.can_chuck_photos():
      return 'The ticket has status {}'.format(self.ticket.status())
    return ''

  def calc_and_set_keep(self, nnow=None):
    nnow = nnow or now()
    if self.ticket.can_chuck_photos():
      self.keep_until = nnow
    else:
      # Near future because I can TOTALLY see myself updating can_chuck_photos
      # to be a bit more sophisiticated, handling abandoned tickets, say.
      self.keep_until = nnow + timedelta(days=30)
    self.keep_forever = False

  def sensitive(self):
    return False
