""" This is for the pages used by maintenance staff to see, resolve, and create
tickets. """
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseRedirect
from django.shortcuts import render, reverse

from work.models.maintenance_ui import (
    maintenance_to_data, handle_maintenance_post_or_error, maintenance_jobs,
    NewTicketForm, save_new_ticket_form, start_new_ticket_form,
    start_new_ticket_form_problem, IGotPaidWrongForm,
    submit_i_got_paid_wrong_form)
from work.models.work_co_worker import WorkCoWorker
from util.admin import admin_context
from util.views import message as html_message


@login_required
def my_tickets(request):
  worker = request.user.worker_or_none
  if not worker or isinstance(worker, WorkCoWorker):
    return html_message('Maintenance', (
        'You need to be an independent service provider in keys for this '
        'page to work.'), 200)
  context = admin_context('Maintenance')
  return render(request, 'work_hihoward_com/my_tickets.html', context=context)


@login_required
def my_tickets_data(request):
  worker = request.user.worker_or_none
  if not worker:
    return JsonResponse({})
  maintenances = []
  data = {'maintenances': maintenances}
  for job in maintenance_jobs(worker.get_child_class_instance()):
    maintenances.append(maintenance_to_data(job))
  return JsonResponse(data)


@login_required
def my_tickets_events(request):
  worker = request.user.worker_or_none
  error = None
  if not worker:
    error = 'You dont seem to be a maintenance worker.'
  else:
    error = handle_maintenance_post_or_error(
        request.POST, worker.get_child_class_instance())
  if error:
    return JsonResponse({'error': error})
  return JsonResponse({'ok': True})


@login_required
def maintenance_new_ticket(request):
  worker = request.user.worker_or_none
  if not worker:
    return html_message('New ticket', (
        'You need to be an independent service provider in keys for this '
        'page to work.'), 200)
  worker = worker.get_child_class_instance()
  form = NewTicketForm(worker)
  message = ''
  if request.method == 'POST':
    form = NewTicketForm(worker, request.POST)
    if form.is_valid():
      if 'start' in request.POST:
        problem = start_new_ticket_form_problem(form, worker)
        if problem:
          message = problem
        else:
          start_new_ticket_form(form, worker)
          return HttpResponseRedirect(reverse('my_tickets'))
      else:
        # The default is 'create' a.k.a. send to tom, in case they submit
        # without clicking
        save_new_ticket_form(form)
        form = NewTicketForm(worker)
        message = 'Saved! Tom will assign.'
  context = {'form': form, 'message': message}
  return render(request, 'work_hihoward_com/new_ticket.html', context=context)


@login_required
def i_got_paid_wrong(request):
  """ I did the whole log_error('actually being used') trick and somebody used
  this in October 2019 """
  worker = request.user.worker_or_none
  if not worker:
    return html_message('I got paid wrong', (
        'You need to be an independent service provider in keys for this '
        'page to work.'), 200)
  worker = worker.get_child_class_instance()
  form = IGotPaidWrongForm(worker)
  noted = False
  if request.method == 'POST':
    form = IGotPaidWrongForm(worker, request.POST)
    if form.is_valid():
      submit_i_got_paid_wrong_form(form, worker)
      noted = True
  context = {'form': form, 'noted': noted}
  return render(
      request, 'work_hihoward_com/i_got_paid_wrong.html', context=context)
