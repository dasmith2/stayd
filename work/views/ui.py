from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
import json

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest, Http404
from django.shortcuts import render, redirect, reverse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.parsers import JSONParser

from errors.models import log_error
from rentals.models.rental import all_city_names, City
from work.models.cleaning import Cleaning
from work.models.work_co import WorkCo
from work.models.inspect import get_cleaner_report, Inspection
from work.models.maintenance import Maintenance
from work.models.not_scheduled_reason import NotScheduledReason
from work.models.one_off import OneOff
from work.models.pay_service_providers import (
    handle_pay_service_providers_post, get_pay_service_provider_payments,
    get_pay_service_provider_table, get_pay_service_provider_totals_table)
from work.models.payment import Payment, STATUSES as PAYMENT_STATUSES
from work.models.raw_event import RawEvent
from work.models.sla import SLAS
from work.models.ticket import Ticket, STATUSES as TICKET_STATUSES, CAME_FROMS
from work.models.ticket_ui import (
    tickets_for_table, tickets_table, edit_ticket_context, REDIRECT_TO_TICKETS,
    NO_SLA)
from work.models.work import Work
from work.models.work_type import WorkType, CLEANER
from work.models.worker import Worker
from rentals.models import Building, Rental
from util.admin import (
    simple_date_range_admin_page, admin_context, dated_admin_context)
from util.background import background
from util.permission import (
    can_groups, user_can_groups, user_in_groups, ACCOUNTANT,
    CLEANING_ADMINISTRATOR_GROUP, VIRTUAL_HOST_GROUP)
from util.timezone import now
from util.urls import date_to_url_str, dates_from_strs


@login_required
@can_groups(VIRTUAL_HOST_GROUP)
def tickets(request, from_date_str='', to_date_str=''):
  from_date, to_date, error = dates_from_strs(from_date_str, to_date_str)
  table = None
  slas = request.GET.getlist('sla', None)
  statuses = request.GET.getlist('status', None)
  not_scheduled_reason_ids = [
      int(id) for id in request.GET.get('not_scheduled_reason_id', [])]
  came_from = request.GET.get('came_from', None)
  cities = list(City.objects.filter(name__in=request.GET.getlist('city', [])))
  building_ids = [int(id) for id in request.GET.getlist('building_id', [])]
  rental_ids = [int(id) for id in request.GET.getlist('rental_id', [])]
  if not error:
    tickets = tickets_for_table(
        from_date, to_date, slas=slas, statuses=statuses,
        not_scheduled_reason_ids=not_scheduled_reason_ids,
        came_from=came_from, cities=cities, building_ids=building_ids,
        rental_ids=rental_ids)
    table = tickets_table(tickets)
  buildings = Building.objects.filter(
      is_active=True).order_by('city', 'nickname')
  rentals = Rental.objects.filter(
      is_active=True, is_test_rental=False).select_related(
          'building').order_by(
              'building__city', 'building__nickname', 'nickname')
  return simple_date_range_admin_page(
      request, from_date_str, to_date_str, date.today() - timedelta(days=14),
      date.today() + timedelta(days=1), 'tickets',
      'Tickets', table=table, template='tickets.html',
      all_slas_for_filters=[NO_SLA] + SLAS, selected_slas=slas,
      all_slas_for_tickets=[''] + SLAS,
      all_statuses=TICKET_STATUSES, selected_statuses=statuses,
      all_not_scheduled_reasons=NotScheduledReason.objects.all(),
      not_scheduled_reason_ids=not_scheduled_reason_ids,
      came_froms=CAME_FROMS, came_from=came_from,
      all_cities=all_city_names(), selected_cities=cities,
      buildings=buildings, building_ids=building_ids,
      rentals=rentals, rental_ids=rental_ids,
      new_ticket_url=reverse('new_ticket'),
      superuser_nav=request.user.is_superuser,
      va_nav=user_in_groups(request.user, VIRTUAL_HOST_GROUP))


@login_required
@can_groups(VIRTUAL_HOST_GROUP)
def set_ticket_sla(request):
  ticket = Ticket.objects.filter(pk=request.POST.get('pk', 0)).first()
  if not ticket:
    raise Http404('This ticket doesn\'t exist')
  sla = request.POST.get('sla', None)
  # sla can be an empty string.
  if sla is None:
    raise Http404('You didn\'t specify an SLA')
  elif sla not in [''] + SLAS:
    raise Http404('SLA {} doesn\'t exist'.format(sla))
  ticket.sla = sla
  ticket.save()
  return JsonResponse({'ok': True})


@login_required
@can_groups(VIRTUAL_HOST_GROUP)
def ticket(request, pk=None):
  ticket = None
  if pk:
    ticket = Ticket.objects.filter(pk=pk).first()
    if not ticket:
      raise Http404('This ticket doesn\'t exist')
  post = None
  if request.method == 'POST':
    post = request.POST
    mark_complete = 'mark_complete' in post
    reschedule = 'reschedule' in post
    duplicate = 'duplicate' in post
    if mark_complete or reschedule or duplicate:
      if mark_complete:
        ticket.mark_completed('{} on {}'.format(
            request.user.username, request.build_absolute_uri))
      elif reschedule:
        ticket.maintenance = None
      elif duplicate:
        new_ticket = ticket.duplicate()
        return redirect(new_ticket.url())
      else:
        raise Exception()
      ticket.save()
      post = None
  context = edit_ticket_context(post, pk)
  if context == REDIRECT_TO_TICKETS:
    return redirect(reverse('tickets'))
  return render(request, 'ticket.html', context=context)


@login_required
def invoice(request, pay_pk):
  pay = Payment.objects.filter(pk=pay_pk).first()
  if not pay:
    raise Http404('This payment doesn\'t exist')
  context = admin_context('Howard', pay=pay.get_child_class_instance())
  return render(request, 'invoice.html', context=context)


@login_required
@can_groups(CLEANING_ADMINISTRATOR_GROUP)
def cleaning_scores(request):
  cleaning = WorkType.objects.get(name=CLEANER)
  cleaners = Worker.objects.filter(
      work_types=cleaning).order_by('name').distinct()
  for cleaner in cleaners:
    cleaner.needs_inspection_score = '?'
    try:
      cleaner.needs_inspection_score = cleaner.needsinspectionscore.score
    except Worker.needsinspectionscore.RelatedObjectDoesNotExist:
      pass
    cleaner.latest_inspection_score = '-'
    inspection = Inspection.objects.for_cleaner(cleaner).first()
    if inspection:
      cleaner.latest_inspection_score = inspection.response.score
  context = admin_context('Cleaning scores', cleaners=cleaners)
  return render(request, 'cleaning_scores.html', context=context)


@login_required
@can_groups(CLEANING_ADMINISTRATOR_GROUP)
def cleaning_score(request, worker_pk):
  cleaner = Worker.objects.filter(pk=worker_pk).first()
  if not cleaner:
    raise Http404('This cleaner doesn\'t exist')
  context = admin_context('Cleaning scores for {}'.format(cleaner.name))
  context.update(get_cleaner_report(cleaner))
  return render(request, 'cleaning_score.html', context=context)


@csrf_exempt
def properly_webhook(request):
  if request.META['REQUEST_METHOD'] == 'POST':
    data_str = json.dumps(JSONParser().parse(request))

    # Save the raw event first in case there's a problem processing it.
    # Then we can go back through and fix the problem.
    raw = RawEvent.objects.create(json=data_str)
    do_properly_webhook(raw.pk)
  return JsonResponse({'ok': True})


@background
def do_properly_webhook(raw_event_id):
  RawEvent.objects.get(pk=raw_event_id).handle()


def redirect_to_pay_service_providers(request):
  # I used this to redirect a few default admin urls.
  return redirect(reverse('pay_service_providers'))


@login_required
@can_groups(CLEANING_ADMINISTRATOR_GROUP, ACCOUNTANT)
def pay_service_provider_totals(request, from_date_str='', to_date_str=''):
  from_date, to_date, error = dates_from_strs(from_date_str, to_date_str)
  table = None
  if not error:
    table = get_pay_service_provider_totals_table(from_date, to_date)
  return simple_date_range_admin_page(
      request, from_date_str, to_date_str, date.today() - timedelta(days=7),
      date.today() + timedelta(days=1), 'pay_service_provider_totals',
      'Pay service provider totals', table=table)


@login_required
@can_groups(CLEANING_ADMINISTRATOR_GROUP, ACCOUNTANT)
def pay_service_providers(request, from_date_str='', to_date_str=''):
  if not from_date_str and not to_date_str:
    return redirect(reverse('pay_service_providers', kwargs={
        'from_date_str': date_to_url_str(date.today() - timedelta(days=7)),
        'to_date_str': date_to_url_str(date.today() + timedelta(days=1))}))
  from_date, to_date, error = dates_from_strs(from_date_str, to_date_str)

  can_send_payments = user_can_groups(
      request.user, CLEANING_ADMINISTRATOR_GROUP)
  payments_kwargs = {}
  try:
    payments_kwargs = _get_payments_kwargs(request)
  except InvalidParameter as ex:
    error = ex.args[0]

  payments_table = None
  if not error:
    payments = get_pay_service_provider_payments(
        from_date, to_date, **payments_kwargs)
    payments_table = get_pay_service_provider_table(
        payments, can_send_payments=can_send_payments,
        can_edit_payments=can_send_payments)
    if request.user.is_superuser:
      handle_pay_service_providers_post(payments, request.POST)

  generate_csv_url = reverse('pay_service_providers_csv', kwargs={
      'from_date_str': from_date_str, 'to_date_str': to_date_str})

  context = dated_admin_context(
      'Pay service providers', from_date, to_date, error, request,
      can_send_payments=can_send_payments,
      generate_csv_url=generate_csv_url, generate_csv_kwargs=payments_kwargs,
      payments_table=payments_table,
      workers=Worker.objects.order_by('name'),
      worker_id=payments_kwargs.get('worker_id', None),
      work_cos=WorkCo.objects.order_by('name'),
      work_co_id=payments_kwargs.get('work_co_id', None),
      owners=Rental.objects.get_owners(),
      owner_id=payments_kwargs.get('owner_id', None),
      buildings=Building.objects.filter(is_active=True).select_related('city'),
      building_id=payments_kwargs.get('building_id', None),
      amount_gte=payments_kwargs.get('amount_gte', ''),
      amount_lt=payments_kwargs.get('amount_lt', ''),
      duration_gte=payments_kwargs.get('duration_gte', ''),
      duration_lt=payments_kwargs.get('duration_lt', ''),
      statuses=PAYMENT_STATUSES,
      status=payments_kwargs.get('status', ''))

  return render(request, 'pay_service_providers.html', context=context)


class InvalidParameter(Exception):
  pass


def _get_payments_kwargs(request):
  kwargs = {}
  for id_key in ('worker_id', 'owner_id', 'building_id', 'work_co_id'):
    got_id = request.GET.get(id_key, None)
    if got_id:
      kwargs[id_key] = int(got_id)
  status = request.GET.get('status', None)
  if status:
    kwargs['status'] = status

  def get_decimal_setting(name, kwargs):
    value = request.GET.get(name, None)
    if value is not None:
      try:
        kwargs[name] = Decimal(value)
      except InvalidOperation:
        raise InvalidParameter('{} should be a decimal'.format(name))
  for name in ['amount_gte', 'amount_lt', 'duration_gte', 'duration_lt']:
    get_decimal_setting(name, kwargs)
  return kwargs


@login_required
@can_groups(CLEANING_ADMINISTRATOR_GROUP, ACCOUNTANT)
def pay_service_providers_csv(request, from_date_str, to_date_str):
  from_date, to_date, date_error = dates_from_strs(from_date_str, to_date_str)
  if date_error:
    return HttpResponseBadRequest('I was unable to parse the dates in the url')
  payments_kwargs = {}
  try:
    payments_kwargs = _get_payments_kwargs(request)
  except Exception as ex:
    return HttpResponseBadRequest(ex.args[0])
  payments = get_pay_service_provider_payments(
      from_date, to_date, **payments_kwargs)
  return get_pay_service_provider_table(payments).csv_response(
      'pay_service_providers.csv')


@login_required
@can_groups(CLEANING_ADMINISTRATOR_GROUP)
def raw_event_detail(request, pk):
  return RawEvent.objects.get(pk=pk).as_html()


@login_required
@can_groups(CLEANING_ADMINISTRATOR_GROUP, VIRTUAL_HOST_GROUP)
def cleaning_history_detail(request, pk):
  cleaning = Cleaning.objects.filter(pk=pk).first()
  if not cleaning:
    raise Http404('This cleaning doesn\'t exist')
  post = None
  if request.method == 'POST':
    post = request.POST
  return work_history_detail(
      request, post, pk, 'Cleaning history', 'cleaning.html',
      link_cleaning_score=True)


def inspection_history_detail(request, pk):
  post = request.method == 'POST' and request.POST
  return work_history_detail(request, post, pk, 'Inspection history')


@login_required
@can_groups(CLEANING_ADMINISTRATOR_GROUP, VIRTUAL_HOST_GROUP)
def one_off_history_detail(request, pk):
  one_off = None
  if pk:
    one_off = OneOff.objects.filter(pk=pk).first()
    if not one_off:
      raise Http404('This one off doesn\'t exist')
  extra_context = {'duplicated': False, 'link_cleaning_score': False}
  post = None
  if request.method == 'POST':
    if 'duplicate' in request.POST:
      one_off.duplicate()
      extra_context['duplicated'] = True
    else:
      post = request.POST
  return work_history_detail(
      request, post, pk, 'One off history', 'one_off.html', **extra_context)


@login_required
@can_groups(CLEANING_ADMINISTRATOR_GROUP)
def repeat_work_history_detail(request, pk):
  post = request.method == 'POST' and request.POST
  return work_history_detail(
      request, post, pk, 'Regular maintenance history')


@login_required
@can_groups(CLEANING_ADMINISTRATOR_GROUP, VIRTUAL_HOST_GROUP)
def maintenance_history_detail(request, pk):
  maintenance = Maintenance.objects.filter(pk=pk).first()
  if not maintenance:
    raise Http404('This Maintenance Job doesn\'t exist')
  post = request.method == 'POST' and request.POST
  return work_history_detail(
      request, post, pk, 'Maintenance history',
      template='maintenance_history.html',
      tickets_table=tickets_table(maintenance.ticket_set.all()))


def work_history_detail(
    request, post, pk, title, template='work.html', **extra_context):
  work = Work.objects.filter(pk=pk).first()
  if not work:
    raise Http404('This job doesn\'t exist')
  work = work.get_child_class_instance()
  payments = []
  payment = work.workpayment_or_none
  payments_table = None
  if payment:
    payments = [payment]
    payments_table = get_pay_service_provider_table(
        payments, can_send_payments=False, can_edit_payments=user_can_groups(
            request.user, CLEANING_ADMINISTRATOR_GROUP))
  # The payments and can_send_payments parameters are for
  # pay_service_providers_table.html
  context = admin_context(
      title, work=work, cancel_error=None, payments=payments,
      payments_table=payments_table)
  if post:
    if 'cancel' in post:
      reason = post.get('cancel_reason', None)
      if reason:
        cancel(work.pk, reason)
        # This is a bit hacky. It assumes we'll successfully cancel that job.
        # Notice there's no save() call here because the actual cancelling
        # happens in def cancel below.
        work.canceled_at = now()
        work.permanently_canceled_reason = reason
      else:
        context['cancel_error'] = 'You must supply a reason'
    else:
      log_error('Confusing post in work_history_detail', post)
  context.update(**extra_context)
  return render(request, template, context=context)


@background
def cancel(work_pk, reason):
  if not settings.DEBUG:
    Work.objects.get(pk=work_pk).cancel(reason)
  else:
    print(
        '\nNot actually canceling because you cant write to net from here.\n')


def old_cleaning_schedule(request):
  return render(
      request, 'old_cleaning_schedule.html',
      context=admin_context('Old cleaning schedule'))


@login_required
@can_groups(CLEANING_ADMINISTRATOR_GROUP, VIRTUAL_HOST_GROUP)
def kick_off_one_off(request, pk):
  one_off = OneOff.objects.get(pk=pk)
  just_started = False
  if not one_off.creation_started:
    just_started = True

  return JsonResponse({
      'just_started': just_started,
      'creation_started': one_off.creation_started,
      'creation_confirmed': one_off.creation_confirmed,
      'creation_error': one_off.creation_error})


@login_required
@can_groups(CLEANING_ADMINISTRATOR_GROUP, VIRTUAL_HOST_GROUP)
def child_class_details(request, pk):
  return redirect(
      Work.objects.get(pk=pk).get_child_class_instance().url())
