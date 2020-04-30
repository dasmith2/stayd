""" The maintenance crew needs a page where they can see what they're doing,
mark tickets complete, and so on. work.hihoward.com """

from datetime import timedelta

from autolink import linkify
from django.db.models import Q
from django import forms
from djmoney.money import Money

from rentals.models import Rental, Building
from util.object_lookup import get_related_object_list_lookup
from util.timezone import now
from work.api import API
from work.models.maintenance import Maintenance, busy
from work.models.payment import ManualPayment
from work.models.ticket import Ticket, WORK_NEW_TICKET, WORK_START_TICKET
from work.models.worker import IndependentWorker


def rental_choices(worker):
  # inactive rentals are allowed here! Why? Because you need to do maintenance
  # on rentals during the onboarding process, which is before they become
  # active.
  rentals = Rental.objects.live_atoms().filter(
      is_test_rental=False, combo_unit_description='').select_related(
          'building').order_by('street', 'apartment')
  choices = []
  for rental in rentals:
    apt = ' {}'.format(rental.apartment) if rental.apartment else ''
    # This is just to filter out testing nonsense locally
    if rental.street or apt:
      label = '{}{}, {}'.format(rental.street, apt, rental.building.city)
      choices.append((rental.pk, label))
  return choices


def building_choices(worker):
  buildings = worker.buildings.filter(is_active=True).order_by('nickname')
  choices = []
  for building in buildings:
    label = building.nickname
    if building.city:
      label += ', {}'.format(building.city)
    choices.append((building.pk, label))
  return choices


def save_new_ticket_form(form):
  data = form.cleaned_data
  return Ticket.objects.create(
      rental_id=int(data['rental']), title=data['description'],
      came_from=WORK_NEW_TICKET)


class NewTicketForm(forms.Form):
  """ On work.hihoward.com """
  def __init__(self, worker, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.fields['rental'] = forms.ChoiceField(
        label='Where', choices=rental_choices(worker))

  description = forms.CharField(label='What\'s up', max_length=300)


MORE = 'More'
LESS = 'Less'
MORE_OR_LESS_CHOICES = (
    (MORE, MORE),
    (LESS, LESS))


class IGotPaidWrongForm(forms.Form):
  """ On work.hihoward.com """
  def __init__(self, worker, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.fields['building'] = forms.ChoiceField(
        label='Where', choices=building_choices(worker))

  more_or_less = forms.ChoiceField(
      label='I should get paid', choices=MORE_OR_LESS_CHOICES,
      widget=forms.RadioSelect)
  amount = forms.DecimalField(label='How much?')
  description = forms.CharField(label='What happened?', max_length=300)


def submit_i_got_paid_wrong_form(form, worker, nnow=None):
  nnow = nnow or now()
  data = form.cleaned_data
  amount = abs(Money(data['amount'], 'USD'))
  if data['more_or_less'] == LESS:
    amount *= -1
  return ManualPayment.objects.create(
      subject='Payment correction',
      message=data['description'],
      worker=worker,
      building=Building.objects.get(pk=data['building']),
      amount=amount,
      work_completed=nnow,
      on_hold_reason='Submitted by {}. Please verify!'.format(worker.name))


def unfinished_today(worker, rental, nnow=None):
  nnow = nnow or now()
  existing_this_worker = Q(
      started_at__isnull=True, offered_to=worker) | Q(accepted_by=worker)
  return Maintenance.objects.filter(
      existing_this_worker,
      rental=rental, offered_start_time__date=nnow.date(),
      completed_at__isnull=True, canceled_at__isnull=True).first()


def get_rental_from_new_ticket_form(form):
  data = form.cleaned_data
  return Rental.objects.get(pk=int(data['rental']))


def start_new_ticket_form_problem(form, worker, nnow=None):
  nnow = nnow or now()
  rental = get_rental_from_new_ticket_form(form)
  existing = unfinished_today(worker, rental, nnow=nnow)
  if not existing and busy(worker, nnow):
    return 'You\'re still working on another job.'


def start_new_ticket_form(form, worker, nnow=None):
  nnow = nnow or now()
  problem = start_new_ticket_form_problem(form, worker, nnow)
  if problem:
    raise Exception(problem)
  data = form.cleaned_data
  rental = get_rental_from_new_ticket_form(form)
  maintenance = unfinished_today(worker, rental, nnow=nnow)
  if maintenance:
    if not maintenance.started_at:
      maintenance.accepted_by = worker
      maintenance.accepted_at = nnow
      maintenance.started_at = nnow
      maintenance.save()
  else:
    maintenance = Maintenance.objects.create(
        rental=rental, title=data['description'],
        accepted_by=worker, accepted_at=nnow, started_at=nnow,
        offered_start_time=nnow, action_on_keys=True)
  maintenance.offered_to.set([worker])
  ticket = Ticket.objects.create(
      rental=rental, title=data['description'],
      came_from=WORK_START_TICKET, manual_start_time=nnow,
      maintenance=maintenance)
  ticket.offered_to.set([worker])
  return ticket


def maintenance_to_data(maintenance):
  tickets = []
  for ticket in maintenance.ticket_set.all().order_by('pk'):
    checklist = []
    if ticket.checklist:
      for item in ticket.checklist.checklistitem_set.order_by('pk'):
        checklist.append(linkify(item.label))
    complete = None
    if ticket.completed_at:
      complete = True
    elif ticket.not_completed_at:
      complete = False
    tickets.append({
        'id': ticket.pk,
        'title': ticket.title,
        'appendix': linkify(ticket.appendix),
        'complete': complete,
        'checklist': checklist,
        'image_url': ticket.image_url})
  when_date = maintenance.get_tz_dt(maintenance.offered_start_time)
  when_date_part = when_date.strftime('%a %b %d')
  when_time_part = when_date.strftime('%I:%M%p')
  if when_date.minute == 0:
    if when_date.hour == 0:
      when_time_part = '00:00'
    elif when_date.hour == 12:
      when_time_part = 'noon'
  rental = maintenance.get_rental()
  where = '{}, {}'.format(
      ' '.join(filter(None, [rental.street, rental.apartment])),
      rental.building.city)
  return {
      'id': maintenance.pk,
      'when': '{} {}'.format(when_date_part, when_time_part),
      'where': where,
      'high_priority': maintenance.high_priority(),
      'started': bool(maintenance.started_at),
      'completed': bool(maintenance.completed_at),
      'tickets': tickets}


def maintenance_jobs(worker, nnow=None):
  """ What jobs make sense to show to a worker? """
  nnow = nnow or now()
  all_jobs = _all_jobs(worker, nnow)
  offered_to_lookup = _get_offered_to_lookup(all_jobs)
  return_jobs = []
  for job in sorted(all_jobs, key=lambda x: x.offered_start_time):
    # There won't be a lookup for a job if the job wasn't actually offered to
    # anybody. In production, ticket_scheduler won't create maintenance that
    # aren't offered to anybody. But this can happen in tests.
    if worker in offered_to_lookup.get(job, {}):
      if job.started_at or job.high_priority():
        return_jobs.insert(0, job)
      else:
        return_jobs.append(job)
  return return_jobs


def _all_jobs(worker, nnow=None):
  nnow = nnow or now()
  return Maintenance.objects.filter(
      Q(accepted_by__isnull=True) | Q(accepted_by=worker),
      offered_start_time__gte=nnow - timedelta(days=1),
      completed_at__isnull=True, canceled_at__isnull=True,
      ticket__isnull=False).distinct().select_related(
          'rental', 'rental__building',
          'accepted_by', 'accepted_by__independentworker')


def _get_offered_to_lookup(jobs):
  """ {job1 -> [Bob, Sam], job2 -> [June]} """
  if not jobs:
    return {}
  job_ids = [str(job.pk) for job in jobs]
  worker_query = """
      SELECT wwot.work_id, wwot.worker_id
      FROM work_work_offered_to AS wwot
      WHERE wwot.work_id IN ({})""".format(','.join(job_ids))
  return get_related_object_list_lookup(
      worker_query, Maintenance, IndependentWorker)


def handle_maintenance_post_or_error(post, worker, nnow=None, api=None):
  nnow = nnow or now()
  api = api or API()
  for key, value in post.items():
    if value:
      started = post.get('start', None)
      stopped = post.get('stop', None)
      reopened = post.get('reopen', None)
      done = post.get('done', None)
      not_done = post.get('not_done', None)
      if done or not_done:
        ticket = Ticket.objects.get(pk=done or not_done)
        if done:
          ticket.mark_completed(
              '{} on work.hihoward.com'.format(worker.name), nnow=nnow)
        elif not_done:
          ticket.mark_incomplete(nnow=nnow)
      elif started or stopped or reopened:
        job = Maintenance.objects.get(pk=started or stopped or reopened)
        job.action_on_keys = True
        if started:
          if job.accepted_by:
            accepted_by = job.accepted_by.get_child_class_instance()
            if accepted_by != worker:
              return '{} already started this job'.format(accepted_by.name)
          job.started_at = nnow
          job.accepted_by = worker
          job.accepted_at = nnow
          if not job.action_on_keys_canceled_on_properly_at and (
              job.job_request_id):
            job.action_on_keys_canceled_on_properly_at = nnow
            job.save()  # Just make sure there's no race
            api.job_request_cancel(job.job_request_id)
        elif stopped:
          # Hey you know, maybe the UI failed to send the reopen. Maybe the
          # user mashed the close button. I don't know. So it's possible a
          # workpayment already exists but it needs to be recreated due to the
          # job actually being done later than we originally thought.
          if job.workpayment_or_none:
            job.workpayment.delete()
          job.completed_at = nnow
        elif reopened:
          if job.workpayment_or_none:
            job.workpayment.delete()
          job.completed_at = None
        job.save()
  return None  # All good!
