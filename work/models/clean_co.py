from collections import namedtuple
from datetime import timedelta

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import reverse

from errors.models import log_error
from rentals.models import Rental
from reservations.models import Reservation, CONFIRMED
from work.models.cleaning import Cleaning
from work.models.work_co import WorkCo
from work.models.message import NEW_CLEAN_CO_WORKER, Message, MessageSender
from work.models.rental import ProperlyRental
from work.models.work import ACCEPTED, STARTED, CANCELED
from work.models.work_co_worker import WorkCoWorker
from work.models.work_line_item import (
    save_work_line_item_formset, get_work_line_item_formset_from_post,
    get_work_line_item_formset_for_work)
from work.models.worker import all_active_workers, Worker
from util import form_fields
from util.background import background
from util.table import Table, Cell
from util.timezone import now, str_to_tz_dt
from util.urls import keys_url


def explain_why_cant_assign_cleaning_to(request_user, cleaning, cleaner):
  """ Worker can be None, which means assign nobody to this cleaning. """
  if cleaner and not cleaner.active:
    return 'This cleaner has been deactivated'
  if cleaning.completed_at:
    return 'This cleaning is finished already.'
  if cleaning.canceled_at:
    return 'This cleaning is canceled'
  if cleaning.job_request_id and not cleaner:
    return (
        'This cleaning is in Properly already. You can pick a new cleaner, '
        'but Properly doesn\'t allow us to remove the only cleaner from a '
        'job. We don\'t really have a great way to swap cleaners on two '
        'jobs that both exist in Properly already. Reach out to Howard for '
        'help.')
  clean_co = WorkCo.objects.filter(owner=request_user).first()
  if not request_user.is_superuser:
    if not clean_co:
      return '{} isnt an owner of a cleaning company.'.format(request_user)
    responsible = cleaning.get_work_co()
    if not responsible:
      return '{} is cleaned by independent cleaners'.format(
          cleaning.rental.nickname)
    if responsible != clean_co:
      return '{} isnt the owner of cleaning company {}'.format(
          request_user, responsible)
    if cleaner and cleaner.work_co != clean_co:
      return '{} doesn\'t work for {}'.format(cleaner.name, clean_co)


def assign_cleaning_to(request_user, cleaning, cleaner, api=None, nnow=None):
  why_not = explain_why_cant_assign_cleaning_to(
      request_user, cleaning, cleaner)
  if why_not:
    raise Exception(why_not)
  if cleaning.accepted_by:
    if cleaning.accepted_by.pk == cleaner.pk:
      return  # Easy.
    cleaning.offered_to.set([cleaner])
    cleaning.accepted_by = None
    cleaning.save()
  else:
    if cleaning.status() in [ACCEPTED, STARTED, CANCELED]:
      subject = 'A work_co cleaning with status {} was assigned'.format(
          cleaning.status())
      log_error(subject, (
          'which is weird, but could be because of that bug I made one '
          'time that cleared out so many assigned tos'))
    if cleaner:
      cleaning.offered_to.set([cleaner])
    elif cleaning.job_request_id:
      raise Exception(
          'You cant remove the only cleaner from a job in properly')
    else:
      cleaning.offered_to.set([])


def cleanings_for_table(clean_co, cleaner, queen_clean, from_date, to_date):
  if int(bool(clean_co)) + int(bool(cleaner)) + int(queen_clean) != 1:
    raise Exception(
        'Specify exactly one of clean_co, cleaner, and queen_clean')
  # .distinct() because otherwise, if a job is offered to more than one person
  # because this used to be an independent service provider situation, this'll
  # return duplicates.
  all_possible = Cleaning.objects.filter(
      Q(offered_to__isnull=False) | Q(canceled_at__isnull=True),
      offered_start_time__date__gte=from_date,
      offered_start_time__date__lt=to_date)
  if cleaner:
    all_possible = all_possible.filter(offered_to=cleaner)
  all_possible = all_possible.distinct().order_by(
      '-offered_start_time').select_related(
          'rental',
          'rental__properlyrental',
          'rental__properlyrental__clean_co',
          'rental__properlyrental__cleaningconfig__cleaning_checklist',
          'reservation',
          'reservation__guest',
          'workpayment',
          'accepted_by',
          'accepted_by__base_user',
          'accepted_by__workcoworker',
          'accepted_by__workcoworker__work_co',
          'accepted_by__independentworker')
  for cleaning in all_possible:
    # If there is no clean_co, then we're in Clean Queen mode and can edit
    # everything.
    if queen_clean or cleaner or (
        clean_co and _clean_co_is_responsible_for_cleaning(
            clean_co, cleaning)):
      yield cleaning


def _clean_co_is_responsible_for_cleaning(clean_co, cleaning):
  # The owner of a cleaning company isn't necessarily an employee of that
  # cleaning company (mainly in tests). So if the person who logs in as the
  # owner of a cleaning company is also logged in as a cleaner who did a
  # cleaning, that cleaning should show up in the list.
  assigned_to_clean_co_owner = cleaning.accepted_by and (
      cleaning.accepted_by.base_user == clean_co.owner)
  return clean_co == cleaning.get_work_co() or assigned_to_clean_co_owner


def _clean_co_properly_rentals(clean_co):
  if clean_co:
    return ProperlyRental.objects.filter(clean_co=clean_co)
  return ProperlyRental.objects.none()


def explain_why_clean_co_cant_edit_cleaning(clean_co, cleaning, nnow=None):
  nnow = nnow or now()
  if cleaning:
    paid_out_already = cleaning.workpayment_or_none and (
        cleaning.workpayment.success())
    if paid_out_already:
      return 'This cleaning is paid out already.'
    # If clean_co is None, we're in Clean Queen mode which isn't limited to a
    # specific cleaning company.
    if clean_co:
      if not _clean_co_is_responsible_for_cleaning(clean_co, cleaning):
        return 'Your cleaning company isn\'t responsible for this cleaning'


def clean_co_can_edit_cleaning(clean_co, cleaning, nnow=None):
  return not explain_why_clean_co_cant_edit_cleaning(
      clean_co, cleaning, nnow=nnow)


def my_cleanings_table(cleaner, from_date, to_date):
  headers = [
      'Action', 'Date', 'Unit', 'Length of stay', 'Status', 'Next checkin',
      'Next guest', 'Reviewed by', 'Reviewed at']
  cleanings = list(cleanings_for_table(
      clean_co=None, cleaner=cleaner, queen_clean=False, from_date=from_date,
      to_date=to_date))
  return _table(
      headers, cleanings, clean_co=None, cleaner=cleaner, admin=False)


def assign_cleanings_table(clean_co, from_date, to_date):
  headers = [
      'Action', 'Date', 'Unit', 'Length of stay', 'Cleaner', 'Status',
      'Next checkin', 'Next guest', 'Total amount', 'Invoice', 'Reviewed by',
      'Reviewed at']
  if not clean_co:
    # If we're not limited to a specific clean_co, we're in Clean Queen mode
    # and should show which cleaning company is responsible for each cleaning.
    headers.append('Cleaning company')
  cleanings = list(cleanings_for_table(
      clean_co=clean_co, cleaner=None, queen_clean=not clean_co,
      from_date=from_date, to_date=to_date))
  return _table(headers, cleanings, clean_co, cleaner=None, admin=True)


def _table(headers, cleanings, clean_co, cleaner, admin, nnow=None):
  nnow = nnow or now()
  action_header = Cell(
      html_content='Action', csv_content='Cleaning ID', is_header=True)
  if headers[0] != 'Action':
    raise Exception(headers)

  table = Table([action_header] + headers[1:])

  following_reservation_lookup = (
      Cleaning.objects.get_following_reservation_lookup(cleanings))
  all_pks = [cleaning.pk for cleaning in cleanings]
  reviewable_lookup = set([cleaning.pk for cleaning in Cleaning.objects.filter(
      pk__in=all_pks, didslide__isnull=False, completed_at__isnull=False)])
  for cleaning in cleanings:
    additional_cleaner_attrs = {
        'data-date': str(cleaning.offered_start_time.date())}
    cleaner_name = ''
    cleaner = cleaning.accepted_by
    if not cleaner:
      offered_to = list(cleaning.offered_to.all())
      if len(offered_to) > 0:
        cleaner = offered_to[0]
    if cleaner:
      additional_cleaner_attrs['data-cleaner-id'] = cleaner.pk
      cleaner_name = cleaner.name
    if admin and not cleaning.completed_at and not cleaning.canceled_at:
      additional_cleaner_attrs['data-editable-cleaner'] = 'true'
    additional_cleaner_attrs['data-cleaning-id'] = cleaning.pk
    cleaner_cell = Cell(
        content=cleaner_name, additional_attrs=additional_cleaner_attrs,
        classes=['assignable'])
    amount_cell = Cell()
    invoice_cell = Cell()
    clean_url = reverse('clean', kwargs={'cleaning_pk': cleaning.pk})
    today = nnow.date() == cleaning.offered_start_time.date()
    action_cell = Cell(
        html_content='', csv_content=cleaning.pk, classes=['actions'],
        additional_attrs={
            'clean_url': clean_url,
            'today': today})
    if admin:
      if clean_co_can_edit_cleaning(clean_co, cleaning):
        action_cell.html_content += (
            '<a href="{}" class="button">Edit</a>'.format(
                reverse('clean_co_cleaning', kwargs={'pk': cleaning.pk})))
      if cleaning.pk in reviewable_lookup:
        action_cell.html_content += cleaning.review_button()
    if cleaner and today and not cleaning.completed_at:
      if _rental_has_cleaning_checklist(cleaning.rental):
        text = 'Clean'
        if cleaning.started_at:
          text = 'Continute'
        action_cell.html_content += (
            '<a class="button clean" href="{}">{}</a>'.format(clean_url, text))
      else:
        action_cell.html_content += (
            '<span class="feedback">{} is missing a cleaning '
            'checklist</span>'.format(cleaning.rental.nickname))
    if cleaning.workpayment_or_none:
      if cleaning.workpayment.can_calculate_amount():
        amount_cell = Cell(cleaning.workpayment.get_total_amount())
        invoice_cell = Cell(
            cleaning.workpayment.invoice_number(),
            url=reverse('invoice', kwargs={'pay_pk': cleaning.workpayment.pk}))
      else:
        log_error(
            'Unable to calculate amount on clean co cleaning',
            'Cleaning {}'.format(cleaning.pk))

    next_checkin = None
    next_guest = None
    next_reservation = cleaning.get_following_reservation(
        following_reservation_lookup=following_reservation_lookup)
    if next_reservation:
      next_checkin = next_reservation.get_check_in()
      # 'Next guest' is for cleaners writing hand written welcome notes for the
      # next guest. If the next guest is a week after the cleaning, it's
      # totally possible that a different guest will show up in the meantime.
      # So only display the next guest if it's so soon after the cleaning we're
      # unlikely to get a new guest in the meantime.
      if next_checkin <= cleaning.offered_start_time + timedelta(days=2):
        next_guest = next_reservation.guest.full_name

    length_of_stay = None
    if cleaning.reservation:
      nights = cleaning.reservation.get_night_count()
      if nights == 1:
        length_of_stay = '1 night'
      else:
        length_of_stay = '{} nights'.format(nights)

    reviewed_by = None
    reviewed_at = None
    if cleaning.reviewed_by:
      reviewed_by = '{} {}'.format(
          cleaning.reviewed_by.username, cleaning.reviewed_by.email)
      reviewed_at = cleaning.get_local_time(cleaning.reviewed_at)
    clean_co_name = None
    responsible = cleaning.get_work_co()
    if responsible:
      clean_co_name = responsible.name
    lookup = {
        'Action': action_cell,
        'Date': cleaning.offered_start_time.date(),
        'Unit': cleaning.rental.nickname,
        'Length of stay': length_of_stay,
        'Cleaner': cleaner_cell,
        'Status': cleaning.status(),
        'Next checkin': next_checkin,
        'Next guest': next_guest,
        'Total amount': amount_cell,
        'Invoice': invoice_cell,
        'Reviewed by': reviewed_by,
        'Reviewed at': reviewed_at,
        'Cleaning company': clean_co_name}
    cells = []
    for header in headers:
      if header not in lookup:
        raise Exception(header)
      cells.append(lookup[header])
    table.create_row(cells)
  return table


def _rental_has_cleaning_checklist(rental):
  properlyrental = rental.properlyrental
  if properlyrental and properlyrental.cleaningconfig_or_none:
    return bool(properlyrental.cleaningconfig.cleaning_checklist)


def _get_where_choices(clean_co, cleaning):
  where_choices = []
  if cleaning:
    # You can't set readonly on an html select, but you can limit the choices
    # to just one option.
    where_choices.append((cleaning.rental.pk, cleaning.rental.nickname))
  else:
    properly_rentals = ProperlyRental.objects.all()
    if clean_co:
      properly_rentals = clean_co.properlyrental_set.all()
    for properly_rental in properly_rentals:
      rental = properly_rental.rental
      where_choices.append((rental.pk, rental.nickname))
  return sorted(where_choices, key=lambda x: x[1])


def _get_assigned_to_choices(clean_co, cleaning):
  if clean_co:
    workers = clean_co.workcoworker_set.filter(
        active_by_cleaning_company=True, active=True)
  else:
    # Queen Clean
    workers = all_active_workers()
  assigned_to_choices = []
  if not cleaning or not cleaning.created_in_properly():
    assigned_to_choices.append((0, ''))
  for worker in workers:
    assigned_to_choices.append((worker.pk, worker.name))
  return assigned_to_choices


class CleaningForm(forms.Form):
  def __init__(self, clean_co, cleaning, *args, **kwargs):
    """ If clean_co is None, we're not limited to a specific cleaning company,
    a.k.a. we're in Queen Clean mode. In that case load all options. """
    super().__init__(*args, **kwargs)
    nnow = kwargs.get('nnow', now())

    self.cleaning = cleaning

    self.fields['where'] = forms.ChoiceField(
        choices=_get_where_choices(clean_co, cleaning))
    self.fields['assigned_to'] = forms.ChoiceField(
        choices=_get_assigned_to_choices(clean_co, cleaning))

    if cleaning and cleaning.reservation:
      self.fields['day'].widget.attrs['readonly'] = True
      self.fields['day'].help_text = (
          'This cleaning is tied to a reservation, so you can\'t change when '
          'it is.')
      # You can't set readonly on an html select, but you can limit the choices
      # to just one option.
      self.fields['where'].help_text = (
          'This cleaning is tied to a reservation, so you can\'t change where '
          'it is.')
      if cleaning.offered_start_time.date() > nnow.date():
        self.fields['started_at'].widget.attrs['readonly'] = True
        self.fields['started_at'].help_text = (
            'This cleaning is in the future, so you can\'t change when it '
            'started yet.')
        self.fields['completed_at'].widget.attrs['readonly'] = True
        self.fields['completed_at'].help_text = (
            'This cleaning is in the future, so you can\'t change when it '
            'was completed yet.')

  where = forms.ChoiceField(choices=[])
  day = form_fields.DateField()
  started_at = form_fields.TimeField(required=False)
  completed_at = form_fields.TimeField(
      required=False, help_text=(
          'If you did the cleaning already, fill this in, and you\'ll get '
          'paid.'))
  assigned_to = forms.ChoiceField(required=False, choices=[])

  def as_table(self):
    try:
      # This is me running my clean function in a different spot so it'll
      # actually throw those Exceptions! Now, here you actually do want to
      # swallow ValidationErrors because maybe the actual data is wrong and you
      # don't want the page to blow up. What I'm really trying to get at here
      # is, don't swallow programming errors.
      self.my_clean()
    except ValidationError:
      pass
    return super().as_table()

  def clean(self, *args, **kwargs):
    # You're not going to believe this, but when you render a form when
    # settings.DEBUG == True, it swallows any errors that occur in clean. But
    # when settings.DEBUG == False, the page breaks! So this is a trap that
    # will make things look OK locally and then totally break in production.
    self.my_clean(*args, **kwargs)
    return super().clean(*args, **kwargs)

  def my_clean(self, *args, **kwargs):
    nnow = kwargs.get('nnow', now())
    if self['completed_at'].value() and not self['assigned_to'].value():
      raise ValidationError('You have to say who completed this cleaning')
    started_at = self.get_started_at()
    completed_at = self.get_completed_at()
    if completed_at and not started_at:
      raise ValidationError(
          'If you say when the cleaning was completed, you should say when it '
          'started.')
    if started_at:
      if started_at > nnow:
        raise ValidationError(
            '"Started at" is in the future. You should only fill in '
            '"Started at" if the cleaning started already.')
      if completed_at:
        if started_at >= completed_at:
          raise ValidationError(
              'Your "Started at" and "Completed at" appear to be in reverse '
              'order')
        if completed_at > nnow:
          raise ValidationError(
              '"Completed at" is in the future. You should only '
              'fill in "Completed at" if the cleaning is done already.')
      if not self.get_assigned_to():
        raise ValidationError(
            'If you say when the cleaning started, you should say who did the '
            'cleaning.')

    if not self.cleaning:
      rental = self.get_rental()
      offered_start_time = self.get_offered_start_time()
      if rental and offered_start_time:
        offered_start_date = offered_start_time.date()
        if Cleaning.objects.filter(
            canceled_at__isnull=True, rental=rental,
            offered_start_time__date=offered_start_date).exists():
          raise ValidationError(
              'There\'s already an active cleaning at {} on {}'.format(
                  rental.nickname, offered_start_date))

  def get_rental(self):
    if self['where'].value():
      return Rental.objects.get(pk=self['where'].value())

  def get_offered_start_time(self):
    if self['day'].value():
      day = str_to_tz_dt(
          str(self['day'].value()),
          tz_str=self.get_rental().building.time_zone)
      return day.replace(hour=11, minute=15)

  def get_started_at(self):
    return self._get_time('started_at')

  def get_completed_at(self):
    return self._get_time('completed_at')

  def get_assigned_to(self):
    assigned_to = int(self['assigned_to'].value())
    if assigned_to:
      return WorkCoWorker.objects.get(pk=assigned_to)

  def _get_time(self, time_field_name):
    day = self.get_offered_start_time()
    if day and self[time_field_name].value():
      # This comes in on a 24 hour clock, despite the widget using AM and PM
      hour, minute = [
          int(part) for part in self[time_field_name].value().split(':')][:2]
      return day.replace(hour=hour, minute=minute)


def cleaning_form_for_cleaning(clean_co, cleaning):
  if not cleaning:
    return CleaningForm(clean_co, cleaning)
  data = {
      'where': cleaning.rental.pk,
      'day': str(cleaning.offered_start_time.date())}

  def _time_string(dt):
    return str(dt.time().replace(second=0, microsecond=0))
  # In order for my_form['day'].value() to return the same type, use the same
  # type here as it uses when you submit a post: strings.
  if cleaning.started_at:
    data['started_at'] = _time_string(cleaning.get_started_at())
  if cleaning.completed_at:
    data['completed_at'] = _time_string(cleaning.get_completed_at())
  who = cleaning.accepted_by or cleaning.offered_to.first()
  if who:
    data['assigned_to'] = who.pk
  else:
    data['assigned_to'] = 0
  return CleaningForm(clean_co, cleaning, data)


EditCleaningPostResult = namedtuple(
    'EditCleaningPostResult',
    'form line_item_formset cleaning saved canceled reopened')


@background
def _cancel(cleaning, permanently_canceled_reason, api):
  cleaning.cancel(permanently_canceled_reason, api=api)


def handle_edit_cleaning_post(
    request_post, clean_co, cleaning, nnow=None, api=None):
  nnow = nnow or now()
  if not clean_co_can_edit_cleaning(clean_co, cleaning):
    raise Exception('clean_co cant edit cleaning {}'.format(cleaning.pk))

  form = cleaning_form_for_cleaning(clean_co, cleaning)
  line_item_formset = get_work_line_item_formset_for_work(cleaning)
  if 'uncancel' in request_post:
    # Otherwise maybe they reloaded the page?
    if cleaning.canceled_at:
      cleaning.reopen()
      cleaning.save()
    return EditCleaningPostResult(
        form=form, line_item_formset=line_item_formset,
        cleaning=cleaning, saved=False, canceled=False, reopened=True)
  elif 'cancel' in request_post:
    _cancel(cleaning, 'Canceled on clean.hihoward.com', api=api)
    return EditCleaningPostResult(
        form=form, line_item_formset=line_item_formset,
        cleaning=cleaning, saved=False, canceled=True, reopened=False)

  form = CleaningForm(clean_co, cleaning, request_post)
  line_item_formset = get_work_line_item_formset_from_post(
      request_post, cleaning)
  if not form.is_valid() or not line_item_formset.is_valid():
    return EditCleaningPostResult(
        form=form, line_item_formset=line_item_formset, cleaning=cleaning,
        saved=False, canceled=False, reopened=False)

  # I reassign cleaning because this might make a new cleaning.
  cleaning = _save_cleaning_form(form, cleaning)
  # I reassign line_item_formset because this might add a few empty slots.
  line_item_formset = save_work_line_item_formset(line_item_formset, cleaning)
  return EditCleaningPostResult(
      form=form, line_item_formset=line_item_formset, cleaning=cleaning,
      saved=True, canceled=False, reopened=False)


def _save_cleaning_form(form, cleaning):
  rental = form.get_rental()
  offered_start_time = form.get_offered_start_time()
  started_at = form.get_started_at()
  completed_at = form.get_completed_at()
  assigned_to = form.get_assigned_to()

  if cleaning:
    cleaning.offered_start_time = offered_start_time
    cleaning.rental = rental
    cleaning.started_at = started_at
    cleaning.completed_at = completed_at
    # canceled_at is set only in obscure corner cases like a) clean co clicks
    # "This cleaning actually happened" but then just leaves the page up b)
    # keys re-cancels the now uncanceled cleaning c) the next day the cleaning
    # company finally fills out the form and submits it.
    cleaning.canceled_at = None
  else:
    # Brand new cleaning case.
    cleaning = Cleaning.objects.create(
        offered_start_time=offered_start_time, rental=rental,
        started_at=started_at, completed_at=completed_at)
  if assigned_to:
    cleaning.offered_to.set([assigned_to])
    if started_at:
      cleaning.accepted_by = assigned_to
      cleaning.action_on_keys = True
  else:
    cleaning.offered_to.set([])
  cleaning.save()
  return cleaning


def current_res_lookup(rentals, nnow=None):
  """ Here I assume that if the reservation is confirmed and the check in is in
  the past, the rental is occupied and will need to be cleaned. """
  nnow = nnow or now()
  lookup = {}
  for reservation in Reservation.objects.filter(
      check_in__lte=nnow, check_out__gte=nnow, rental__in=rentals,
      status=CONFIRMED).select_related('rental'):
    lookup[reservation.rental] = reservation
  return lookup


def next_res_w_cleaning_lookup(rentals, nnow=None):
  """ Here I don't assume a reservation is valid until it has a cleaning, which
  doesn't happen until the id is verified and such. Also, cleaning companies
  don't assign a cleaning until it exists obviously, so if the All Rentals
  table says there's an upcoming reservation but that reservation doesn't have
  a cleaning yet because the id isn't verified or whatever, the cleaning
  company may be like, "Hey, the all rentals table says there's a reservation
  coming up after but there's no cleaning to assign in my list." """
  nnow = nnow or now()
  lookup = {}
  for reservation in Reservation.objects.filter(
      check_in__gt=nnow, rental__in=rentals, status=CONFIRMED,
      cleaning__isnull=False).distinct().select_related(
          'rental').order_by('check_in'):
    if reservation.rental not in lookup:
      lookup[reservation.rental] = reservation
  return lookup


def all_rentals_table(clean_co, nnow=None):
  nnow = nnow or now()
  rentals = Rental.objects.filter(
      properlyrental__clean_co=clean_co, is_active=True).order_by(
      'building__nickname', 'apartment').select_related('building')
  current_reservation_lookup = current_res_lookup(
      rentals, nnow=nnow)
  next_reservation_lookup = next_res_w_cleaning_lookup(rentals, nnow=nnow)
  table = Table([
      'Building', 'Rental', 'Bedrooms', 'Bathrooms', 'Vacant',
      'Current check out', 'Total nights', 'Next check in', 'Total nights'])
  for rental in rentals:
    current_reservation = current_reservation_lookup.get(rental, None)
    current_check_out = current_reservation and (
        current_reservation.get_check_out())
    current_nights = current_reservation and (
        current_reservation.get_night_count())
    next_reservation = next_reservation_lookup.get(rental, None)
    next_check_in = next_reservation and next_reservation.get_check_in()
    next_nights = next_reservation and next_reservation.get_night_count()
    # One time, the apartment field wasn't filled in but you could see it in
    # the nickname.
    apartment = rental.apartment or rental.nickname
    table.create_row([
        rental.building.nickname, apartment, rental.bedrooms,
        rental.bathrooms, not bool(current_reservation), current_check_out,
        current_nights, next_check_in, next_nights])
  return table


class WorkCoWorkerForm(forms.Form):
  name = forms.CharField(max_length=200)
  phone = forms.CharField(
      max_length=50,
      help_text='Please include a country code, for instance, +1(555)555-5555')
  email = forms.CharField(max_length=100, help_text=(
      'Note: you can\'t change the email of an active service provider.'))

  def __init__(self, work_co_worker, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.work_co_worker = work_co_worker

  def clean(self, *args, **kwargs):
    email = self['email'].value()
    new_worker = not self.work_co_worker or not self.work_co_worker.pk
    if email and new_worker and Worker.objects.filter(email=email).exists():
      raise ValidationError(
          'Worker with email {} already exists'.format(email))
    return super().clean(*args, **kwargs)

  def possibly_deactivate_email(self, work_co_worker):
    # You can't change a cleaner's email address because that's the same thing
    # as creating a totally new worker in Properly.
    if work_co_worker.active:
      self.fields['email'].widget.attrs['readonly'] = True

  def save_new(self, clean_co, message_sender=None):
    message_sender = message_sender or MessageSender()
    if not self.is_valid():
      raise Exception('You cant save an invalid form')
    data = self.data
    cleaner = WorkCoWorker.objects.create(
        work_co=clean_co,
        name=data['name'],
        phone=data['phone'],
        # I think somebody is using the clean_co admin from a phone which is
        # capitalizing the first letter of emails. This foils the unique
        # constraint on the email column AND confuses Properly, which treats
        # differently capitalized emails as the same in some spots and
        # different in others, a.k.a. Properly chokes.
        email=data['email'].lower(),
        active=False)
    url = keys_url(
        reverse('admin:work_workcoworker_change', args=(cleaner.pk,)))
    content = (
        'A new cleaning company cleaner has been added to Keys. Go to '
        'Trainual and assign them to the Training-Cleaning company cleaner '
        'role.\n\n'
        '{}\n\nName: {}\nPhone: {}\nEmail: {}\nCleaning company: {}').format(
            url, cleaner.name, cleaner.phone, cleaner.email, clean_co.name)
    Message.objects.create_and_send_email(
        to=settings.ALERT_NEW_CLEAN_CO_WORKER, reason=NEW_CLEAN_CO_WORKER,
        content=content, work=None, message_sender=message_sender)

  def save_existing(self, work_co_worker):
    if not self.is_valid():
      raise Exception('You cant save an invalid form')
    data = self.data
    work_co_worker.name = data['name']
    work_co_worker.phone = data['phone']
    if work_co_worker.active:
      if work_co_worker.email != data['email']:
        raise Exception(
            'You cant change the email of an active service provider')
    else:
      work_co_worker.email = data['email']
    work_co_worker.save()


def handle_cleaner_save(post, pk, clean_co, message_sender=None):
  work_co_worker = None
  if pk:
    work_co_worker = WorkCoWorker.objects.get(pk=pk)
  form = WorkCoWorkerForm(work_co_worker, post)
  if form.is_valid():
    if work_co_worker:
      form.possibly_deactivate_email(work_co_worker)
      form.save_existing(work_co_worker)
    else:
      form.save_new(clean_co, message_sender=message_sender)
  return form
