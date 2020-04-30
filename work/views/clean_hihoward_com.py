from datetime import date, timedelta
import json
import re

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, Http404
from django.shortcuts import render, redirect, reverse

from errors.models import notify
from work.models.clean import (
    handle_report_cleaning_ticket,
    handle_slide_did_stuff, handle_complete_cleaning, slides_for_clean,
    created_tickets_data, created_ticket_data)
from work.models.cleaning import Cleaning
from work.models.cleaning_checklist import Slide
from work.models.clean_co import (
    WorkCoWorkerForm, handle_cleaner_save, handle_edit_cleaning_post,
    assign_cleanings_table, my_cleanings_table,
    WorkCoWorker, explain_why_cant_assign_cleaning_to,
    assign_cleaning_to, all_rentals_table, clean_co_can_edit_cleaning,
    cleaning_form_for_cleaning, explain_why_clean_co_cant_edit_cleaning)
from work.models.ticket import Ticket
from work.models.work_co import WorkCo
from work.models.work_line_item import (
    get_work_line_item_formset_for_work)
from work.models.worker import Worker
from util.admin import (
    simple_date_range_admin_page, simple_table_page, admin_context)
from util.ajax import AjaxProblem, ajax, OK
from util.permission import user_can_groups, CLEANING_ADMINISTRATOR_GROUP
from util.timezone import now
from util.urls import dates_from_strs


CLEANCO_SITE_HEADER = 'Howard cleaning company administration'


@login_required
def review_cleaning(request, pk):
  cleaning = Cleaning.objects.filter(pk=pk).first()
  if not cleaning:
    return Http404('Cleaning does not exist')
  problem = None
  title = 'Review cleaning'
  got_slides_for_clean = []
  if not cleaning.completed_at:
    problem = 'This cleaning isn\'t complete yet'
  elif not cleaning.get_cleaning_checklist():
    problem = 'This rental doesn\'t have a cleaning checklist yet'
  else:
    cleaning.reviewed_by = request.user
    cleaning.reviewed_at = now()
    cleaning.save()
    got_slides_for_clean = slides_for_clean(cleaning)['slides']
  context = admin_context(
      title, problem=problem, back_to_list_url=reverse('clean_co_cleanings'),
      cleaning=cleaning, slides_for_clean=got_slides_for_clean,
      **shared_clean_hihoward_context(request))
  return render(
      request, 'clean_hihoward_com/review_cleaning.html', context=context)


@login_required
def clean(request, cleaning_pk):
  """ clean is a verb here. Do a cleaning. """
  cleaning = Cleaning.objects.filter(pk=cleaning_pk).first()
  cleaning_checklist = None
  problem = None
  if not cleaning:
    return Http404('Cleaning does not exist')
  title = 'Clean'
  done_url = None
  doing_slides_url = None
  cleaner = None
  for next_cleaner in cleaning.offered_to.all():
    if next_cleaner.base_user == request.user:
      cleaner = next_cleaner
  if cleaning:
    if not cleaner:
      problem = 'This cleaning isn\'t assigned to you'
    elif not cleaning.offered_start_time.date() == date.today():
      problem = 'You can only do this cleaning on {}'.format(
          cleaning.offered_start_time.date())
    elif cleaning.completed_at:
      problem = 'This cleaning is done already'
    else:
      if not cleaning.started_at:
        cleaning.started_at = now()
        cleaning.accepted_by = cleaner
        cleaning.save()
      cleaning_checklist = (
          cleaning.rental.properlyrental.cleaningconfig.cleaning_checklist)
      if not cleaning_checklist:
        problem = '{} doesn\'t have a cleaning checklist'.format(
            cleaning.rental.nickname)
    title = 'Clean {} on {}'.format(
        cleaning.rental.nickname, cleaning.offered_start_time.date())
    done_url = reverse(
        'complete_cleaning', kwargs={'cleaning_pk': cleaning.pk})
    doing_slides_url = reverse(
        'doing_slides', kwargs={'cleaning_pk': cleaning.pk})
  else:
    problem = 'Cleaning does not exist'
  report_cleaning_ticket_url = reverse(
      'report_cleaning_ticket', kwargs={'cleaning_pk': cleaning.pk})
  context = admin_context(
      title, site_header=CLEANCO_SITE_HEADER, site_title=title,
      cleaning=cleaning, cleaning_checklist=cleaning_checklist,
      problem=problem, image_host=settings.PUBLIC_IMAGE_HOST,
      created_tickets=json.dumps(created_tickets_data(cleaning)),
      done_url=done_url,
      back_to_list_url=reverse('clean_co_cleanings'),
      doing_slides_url=doing_slides_url,
      report_cleaning_ticket_url=report_cleaning_ticket_url,
      access_items=access_items_for_rental(cleaning.rental),
      **shared_clean_hihoward_context(request))
  return render(
      request, 'clean_hihoward_com/clean.html', context=context)


def access_items_for_rental(rental):

  class AccessItem(object):
    def __init__(self, name, value):
      self.name = name
      self.value = value

    def __str__(self):
      if self.value.find('http') == 0:
        return '<a href="{}">{}</a>'.format(self.value, self.name)
      return '{}: {}'.format(self.name, self.value)

  access_codes = rental.main_property_access_codes_in_order_of_use
  access_items = [
      AccessItem('Access codes', access_codes),
      AccessItem('Backup check-in codes', rental.backup_check_in_codes),
      AccessItem('WiFi', rental.wifi_network_name),
      AccessItem('WiFi password', rental.wifi_password),
      AccessItem('Extra details', rental.extra_details),
      AccessItem(
          'Main checkin instructions', rental.main_checkin_instructions_link),
      AccessItem(
          'Backup check-in instructions link',
          rental.backup_check_in_instructions_link),
      AccessItem(
          'Main checkin instructions', rental.parking_link)]
  return [access_item for access_item in access_items if access_item.value]


@login_required
@ajax
def doing_slides(request, cleaning_pk):
  return slides_for_clean(_get_cleaning(cleaning_pk))


@login_required
@ajax
def complete_cleaning(request, cleaning_pk):
  handle_complete_cleaning(_get_cleaning(cleaning_pk))
  return OK


@login_required
@ajax
def report_cleaning_ticket(request, cleaning_pk):
  return created_ticket_data(
      handle_report_cleaning_ticket(request.POST, _get_cleaning(cleaning_pk)))


@login_required
@ajax
def close_ticket(request, ticket_pk):
  """ When a cleaner reports an issue, the cleaning company has a link to mark
  the ticket resolved, which is important when the ticket is, like, "The vacuum
  cleaner bag is full," and the clean co is just, like, "Replace the vacuum
  cleaner bag and do the cleaning you weirdo." """
  ticket = Ticket.objects.filter(pk=ticket_pk).first()
  if not ticket:
    raise AjaxProblem('This ticket doesnt exist')
  ticket.completed_at = now()
  ticket.save()
  return OK


@login_required
@ajax
def slide_done(request, cleaning_pk, slide_pk):
  handle_slide_did_stuff(
      request.POST, _get_cleaning(cleaning_pk), _get_slide(slide_pk))
  return OK


def _get_slide(slide_pk):
  slide = Slide.objects.filter(pk=slide_pk).first()
  if not slide:
    raise AjaxProblem('Slide does not exist')
  return slide


def _get_cleaning(cleaning_pk):
  cleaning = Cleaning.objects.filter(pk=cleaning_pk).first()
  if not cleaning:
    raise AjaxProblem('Cleaning does not exist')
  return cleaning


def can_queen_clean(request):
  return user_can_groups(request.user, CLEANING_ADMINISTRATOR_GROUP)


def shared_clean_hihoward_context(request):
  can_administer_cleanings = _clean_co(request) or user_can_groups(
      request.user, CLEANING_ADMINISTRATOR_GROUP)
  return {
      'can_administer_cleanings': can_administer_cleanings,
      'clean_co_cleanings_url': reverse('clean_co_cleanings'),
      'all_rentals_url': reverse('clean_co_all_rentals'),
      'cleaners_url': reverse('cleaners')}


@login_required
def clean_co_cleanings(request, from_date_str='', to_date_str=''):
  from_date, to_date, error = dates_from_strs(from_date_str, to_date_str)
  table = None
  clean_co = _clean_co(request)
  cleaners = []
  problem = None
  i_am_worker_pk = None
  if not error:
    if clean_co:
      cleaners = clean_co.workcoworker_set.filter(
          active=True, active_by_cleaning_company=True)
      table = assign_cleanings_table(clean_co, from_date, to_date)
    elif can_queen_clean(request):
      cleaners = WorkCoWorker.objects.filter(
          active=True, active_by_cleaning_company=True)
      table = assign_cleanings_table(clean_co, from_date, to_date)
    else:
      i_am_worker = Worker.objects.filter(base_user=request.user).first()
      if i_am_worker:
        i_am_worker_pk = i_am_worker.pk
        table = my_cleanings_table(i_am_worker, from_date, to_date)
      else:
        problem = (
            'Uh... there seems to be a configuration issue. I notified the '
            'staff at Howard. Thanks for your patience!')
        subject = 'Configuration issue: {} isn\'t a service provider'.format(
            request.user.username)
        message = (
            'Go to Keys and look for "Service providers: work for a company". '
            '{username} needs to be set up as the "Base user" of one of '
            'these service providers in order to use clean.hihoward.com. '
            'This is how keys knows what cleaning company {username} '
            'works for.\n\nAlternately, if {username} is the owner of a '
            'cleaning company, look under "Cleaning companies" on '
            'keys.').format(username=request.user.username)
        notify(settings.ALERT_CLEANING_CONFIGURATION_ISSUES, subject, message)
  return simple_date_range_admin_page(
      request, from_date_str, to_date_str, date.today() - timedelta(days=7),
      date.today() + timedelta(days=8), 'clean_co_cleanings',
      '', table=table, i_am_worker_pk=i_am_worker_pk,
      template='clean_hihoward_com/cleanings.html',
      site_header=CLEANCO_SITE_HEADER, site_title='Assign cleanings',
      cleaners=cleaners, problem=problem,
      **shared_clean_hihoward_context(request))


@login_required
def clean_co_cleaning(request, pk=None):
  clean_co = _clean_co(request)
  problem = None
  if not clean_co and not can_queen_clean(request):
    problem = 'You don\'t appear to be the owner of a cleaning company'
  cleaning = None
  if pk:
    cleaning = Cleaning.objects.filter(pk=pk).first()
  if pk and not cleaning:
    return Http404('Cleaning does not exist')
  form = None
  line_item_formset = None
  if clean_co_can_edit_cleaning(clean_co, cleaning):
    if request.method == 'POST':
      edit_cleaning_result = handle_edit_cleaning_post(
          request.POST, clean_co, cleaning)
      if edit_cleaning_result.saved and not cleaning:
        return redirect(reverse('clean_co_cleaning', kwargs={
            'pk': edit_cleaning_result.cleaning.pk}))
      elif edit_cleaning_result.canceled:
        return redirect(reverse('clean_co_cleanings'))
      form = edit_cleaning_result.form
      line_item_formset = edit_cleaning_result.line_item_formset
      cleaning = edit_cleaning_result.cleaning
    else:
      form = cleaning_form_for_cleaning(clean_co, cleaning)
      line_item_formset = get_work_line_item_formset_for_work(cleaning)
  else:
    problem = 'You can\'t edit this cleaning. {}'.format(
        explain_why_clean_co_cant_edit_cleaning(clean_co, cleaning))
  title = 'New cleaning'
  reopen_text = ''
  if cleaning:
    title = 'Edit cleaning: {} {}'.format(
        cleaning.rental.nickname, cleaning.offered_start_time.date())
    if cleaning.canceled_at:
      if cleaning.offered_start_time > now():
        reopen_text = 'This cleaning will actually happen'
      else:
        reopen_text = 'This cleaning actually happened'
  context = admin_context(
      title, site_header=CLEANCO_SITE_HEADER, site_title=title,
      cleaning=cleaning, problem=problem, form=form, reopen_text=reopen_text,
      line_item_formset=line_item_formset,
      cleaning_list_url=reverse('clean_co_cleanings'),
      **shared_clean_hihoward_context(request))
  return render(
      request, 'clean_hihoward_com/clean_co_cleaning.html', context=context)


@login_required
def clean_co_all_rentals(request):
  """ This is actually being used daily as of 9/23/19 """
  error = None
  table = None
  clean_co = _clean_co(request)
  if clean_co:
    table = all_rentals_table(clean_co=clean_co)
  else:
    error = 'You don\'t appear to be the owner of a cleaning company'
  return simple_table_page(
      request, 'clean_co_all_rentals', '', table=table, error=error,
      template='clean_hihoward_com/all_rentals.html',
      **shared_clean_hihoward_context(request))


@login_required
def cleaners(request):
  problem = None
  clean_co = _clean_co(request)

  if clean_co and request.method == 'POST':
    for key in request.POST.keys():
      got_match = re.compile(r'deactivate_(\d+)').match(key)
      if got_match:
        cleaner = WorkCoWorker.objects.get(pk=int(got_match.groups()[0]))
        if cleaner.work_co == clean_co:
          cleaner.active_by_cleaning_company = False
          cleaner.save()
        else:
          problem = '{} doesn\'t appear to work for {}'.format(
              cleaner.name, clean_co.name)

  cleaners = []
  if clean_co:
    # There are 2 reasons you might be inactive. You haven't completed training
    # yet, or you've been deactivated. Ideally we should be able to tell these
    # use cases apart so we can show incomplete-training and hide inactive
    # cleaners here.
    cleaners = clean_co.workcoworker_set.filter(
        active_by_cleaning_company=True)
  else:
    problem = 'You don\'t appear to be the owner of a cleaning company.'

  add_new_cleaner_url = reverse('cleaner', kwargs={'pk': 0})
  context = admin_context(
      '', site_header=CLEANCO_SITE_HEADER, site_title='Manage cleaners',
      cleaners=cleaners, problem=problem,
      add_new_cleaner_url=add_new_cleaner_url,
      **shared_clean_hihoward_context(request))
  return render(request, 'clean_hihoward_com/cleaners.html', context=context)


@login_required
def cleaner(request, pk):
  pk = int(pk)
  cleaner = None
  problem = None
  if pk:
    cleaner = WorkCoWorker.objects.filter(pk=pk).first()
    if not cleaner:
      raise Http404('This cleaner doesn\'t exist')
  if request.method == 'POST':
    form = handle_cleaner_save(request.POST, pk, _clean_co(request))
    if form.is_valid():
      return redirect(reverse('cleaners'))
  else:
    if pk:
      form = WorkCoWorkerForm(cleaner, {
          'name': cleaner.name,
          'phone': cleaner.phone,
          'email': cleaner.email})
      form.possibly_deactivate_email(cleaner)
    else:
      form = WorkCoWorkerForm(cleaner)
  context = admin_context(
      '', site_header=CLEANCO_SITE_HEADER, site_title='Edit cleaner',
      form=form, problem=problem, **shared_clean_hihoward_context(request))
  return render(request, 'clean_hihoward_com/cleaner.html', context=context)


@login_required
def set_cleaning_cleaner(request, cleaning_pk, cleaner_pk):
  cleaning = Cleaning.objects.get(pk=cleaning_pk)
  cleaner = None
  if cleaner_pk:
    cleaner = WorkCoWorker.objects.get(pk=cleaner_pk)

  why_not = explain_why_cant_assign_cleaning_to(
      request.user, cleaning, cleaner)
  if why_not:
    return JsonResponse({'error': why_not})

  assign_cleaning_to(request.user, cleaning, cleaner)
  return JsonResponse({'ok': True})


def _clean_co(request):
  return WorkCo.objects.filter(owner=request.user).first()
