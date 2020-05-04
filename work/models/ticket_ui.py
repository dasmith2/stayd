from django import forms
from django.forms import widgets
from django.shortcuts import reverse

from rentals.models import Rental
from util.admin import admin_context
from util.table import Table, Cell
from util.timezone import now
from work.models.maintenance_checklist import (
    MaintenanceChecklist, ChecklistItem)
from work.models.rental import ProperlyRental
from work.models.ticket import Ticket, INCOMPLETE, TICKETS_PAGE


NO_SLA = 'No SLA'


def tickets_for_table(
    from_date, to_date, slas=None, statuses=None,
    not_scheduled_reason_ids=None, came_from=None, cities=None,
    building_ids=None, rental_ids=None):
  """ from_date and to_date refer to when the tickets were created. """
  to_return = []
  # These select_relateds are what makes the tickets page run fast even when
  # the team pulls back ALL THE TICKETS FROM 2019!! or whatever
  for ticket in Ticket.objects.filter(
      created_at__date__gte=from_date,
      created_at__date__lt=to_date).select_related(
          'checklist',
          'maintenance',
          'maintenance__accepted_by',
          'not_scheduled_reason',
          'rental',
          'rental__building',
          'work_type'):
    if slas:
      if NO_SLA in slas and not ticket.sla:
        pass
      elif ticket.sla not in slas:
        continue
    if statuses and ticket.status() not in statuses:
      continue
    if not_scheduled_reason_ids:
      int_not_scheduled_reason_ids = [
          int(id) for id in not_scheduled_reason_ids]
      if ticket.not_scheduled_reason_id not in int_not_scheduled_reason_ids:
        continue
    if came_from:
      if ticket.came_from != came_from:
        continue
    if cities and ticket.rental.building.city not in cities:
      continue
    if building_ids:
      int_building_ids = [int(building_id) for building_id in building_ids]
      if ticket.rental.building_id not in int_building_ids:
        continue
    if rental_ids:
      int_rental_ids = [int(rental_id) for rental_id in rental_ids]
      if ticket.rental_id not in int_rental_ids:
        continue
    to_return.append(ticket)

  def minutes_from_now(ticket):
    big_number = 5 * 365 * 24 * 60 * 60  # Like, 5 years in seconds
    if ticket.completed_at:
      # The longer ago they were completed, the lower down the list they are.
      return 2 * big_number + (now() - ticket.completed_at).total_seconds()
    if ticket.maintenance:
      return (ticket.maintenance.offered_start_time - now()).total_seconds()
    return big_number - (now() - ticket.created_at).total_seconds()
  return sorted(to_return, key=minutes_from_now)


def tickets_table(tickets, nnow=None):
  scheduled_for_header = Cell(
      'Scheduled for', classes=['sorted'], is_header=True)
  table = Table([
      'Title', 'City', 'Rental', 'SLA', 'Status', 'Created', 'Completed on',
      'Completed by', 'Time to completion', 'Maintenance job',
      scheduled_for_header, 'Last schedule attempt', 'Why can\'t schedule',
      'Came from'])
  for ticket in tickets:
    title_cell = Cell(ticket.title, url=ticket.url())
    not_reason = (
        ticket.not_scheduled_reason and ticket.not_scheduled_reason.name)
    maintenance_cell = Cell()
    scheduled_for = None
    if ticket.maintenance:
      maintenance_cell = Cell(
          ticket.maintenance.get_title()[:30], url=ticket.maintenance.url())
      scheduled_for = ticket.maintenance.offered_start_time
    time_to_completion = None
    if ticket.completed_at:
      time_to_completion = ticket.completed_at - ticket.created_at
    sla_cell = Cell(
        ticket.sla, classes=['sla'],
        additional_attrs={'data-can-edit-sla': ticket.can_edit_everything()})
    table.create_row([
        title_cell, ticket.rental.building.city.name,
        ticket.rental.nickname, sla_cell, ticket.status(nnow=nnow),
        ticket.created_at, ticket.completed_at,
        ticket.completed_by_description, time_to_completion, maintenance_cell,
        scheduled_for, ticket.last_attempt_to_schedule, not_reason,
        ticket.came_from], additional_attrs={'data-pk': ticket.pk})
  return table


def get_line_item_form_set(checklist, request_post=None):
  LineItemFormset = forms.modelformset_factory(
      ChecklistItem, fields=('label',), extra=3,
      widgets={'label': widgets.TextInput()}, can_delete=True)
  formset = LineItemFormset(
      request_post,
      queryset=ChecklistItem.objects.filter(
          checklist__pk=checklist and checklist.pk))
  return formset


class TicketFormEverything(forms.ModelForm):
  """ Super users on new tickets. """
  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.fields['rental'].queryset = Rental.objects.live_atoms()

  class Meta:
    exclude = (
        'maintenance', 'created_at', 'completed_at',
        'last_attempt_to_schedule', 'not_scheduled_reason', 'checklist',
        'existing_checklist_url', 'came_from', 'came_from_work', 'external_id',
        'image_url')
    model = Ticket


class TicketFormSLA(forms.ModelForm):
  """ Super users on scheduled tickets. """
  class Meta:
    fields = ('sla', 'internal_notes')
    model = Ticket


class TicketFormJustNotes(forms.ModelForm):
  """ Virtual hosts on scheduled tickets, super users on completed tickets. """
  class Meta:
    fields = ('internal_notes',)
    model = Ticket


REDIRECT_TO_TICKETS = 'redirect to tickets'


def ticket_edit_form(pk):
  """
  Who can edit what? Well, everybody can always edit notes. A ticket with a
  canceled maintenance counts as a new ticket. You can edit everything on a new
  ticket. If the ticket's maintenance was started already, you can only do sla
  (and notes).
  """
  # New ticket
  if not pk:
    return TicketFormEverything
  # The view already returned a 404 if this ticket doesn't exist.
  ticket = Ticket.objects.get(pk=pk)
  if ticket.can_edit_everything():
    return TicketFormEverything

  # Completed ticket
  if ticket.completed_at:
    return TicketFormJustNotes

  # Started ticket
  return TicketFormSLA


def edit_ticket_context(post, pk):
  """ Holy cow django forms and model forms and formsets and such are a bit of
  a mess. """
  title = 'New ticket'
  ticket = None
  checklist = None
  line_items_forms = None
  FormClass = ticket_edit_form(pk)
  can_edit_everything = True
  can_edit_anything = True
  if pk:
    ticket = Ticket.objects.get(pk=pk)
    can_edit_everything = ticket.can_edit_everything()
    can_edit_anything = ticket.can_edit_anything()
    if can_edit_anything:
      title = 'Edit ticket'
    else:
      title = 'Ticket'
    checklist = ticket.checklist
  if post:
    ticket_form = FormClass(post, instance=ticket)
    if ticket_form and ticket_form.is_valid():
      ticket = ticket_form.save()
      if not ticket.came_from:
        ticket.came_from = TICKETS_PAGE
        ticket.save()
      if can_edit_everything:
        existing_checklist_url = post.get('existing_checklist_url', '')
        if existing_checklist_url:
          ticket.existing_checklist_url = existing_checklist_url
          ticket.checklist = None
          ticket.save()
          return REDIRECT_TO_TICKETS
        else:
          line_items_forms = get_line_item_form_set(checklist, post)
          if line_items_forms.is_valid():
            if _save_checklist(ticket, checklist, line_items_forms):
              return REDIRECT_TO_TICKETS
      else:
        return REDIRECT_TO_TICKETS
  else:
    ticket_form = FormClass(instance=ticket)
    if can_edit_everything:
      line_items_forms = get_line_item_form_set(checklist)
  existing_checklist_url = (ticket and ticket.existing_checklist_url) or ''
  work = ticket and ticket.maintenance
  return admin_context(
      title, tickets_url=reverse('tickets'), ticket_form=ticket_form,
      line_items_forms=line_items_forms,
      existing_checklist_url=existing_checklist_url,
      can_edit_anything=can_edit_anything,
      can_edit_everything=can_edit_everything,
      can_reschedule=ticket and ticket.status() == INCOMPLETE,
      work=work,
      ticket=ticket, tickets_table=ticket and tickets_table([ticket]))


def _save_checklist(ticket, checklist, line_items_forms):
  ticket.existing_checklist_url = ''
  ticket.save()
  if checklist:
    for lif in line_items_forms:
      if lif.is_valid():
        label = lif.cleaned_data.get('label', '')
        delete = lif.cleaned_data.get('DELETE', False)
        if lif.cleaned_data.get('id', None):
          if delete:
            lif.instance.delete()
          else:
            lif.instance.label = label
            lif.instance.save()
        elif label and not delete:
          checklist.add_task(label)
    return True
  else:
    properly_rental = ProperlyRental.objects.filter(
        rental=ticket.rental).first()
    if not properly_rental:
      properly_rental = ProperlyRental.objects.create(
          rental=ticket.rental)
    checklist = MaintenanceChecklist.objects.create(
        properly_rental=properly_rental, title=ticket.title[:200])
    ticket.checklist = checklist
    ticket.save()
    for lif in line_items_forms:
      if lif.is_valid() and lif.cleaned_data.get('label', ''):
        checklist.add_task(lif.cleaned_data['label'])
  return True
