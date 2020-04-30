from django import forms
from django.contrib import admin
from django.contrib.admin.views.main import ChangeList
from django.core.exceptions import ValidationError
from django.forms import BaseModelFormSet
from django.shortcuts import reverse
from django.utils.safestring import mark_safe
from django.utils.html import format_html

from work.models.cleaning import CleaningConfig, Cleaning
from work.models.cleaning_checklist import CleaningChecklist
from work.models.inspect import Inspection
from work.models.work_co import WorkCo
from work.models.work_co_worker import WorkCoWorker
from work.models.work import CREATED
from work.models.work_type import WorkType
from work.models.worker import IndependentWorker
from work.models.repeat_work import RepeatConfig, RepeatWork
from work.models.maintenance import Maintenance
from work.models.message import SubjectLine, Message
from work.models.one_off import OneOff, LineItem
from work.models.payment import ManualPayment, WorkPayment
from work.models.raw_event import RawEvent
from work.models.rental import ProperlyRental
from rentals.models import Rental
from util.admin import ModelAdmin
from util.templatetags.util_extras import currency


@admin.register(CleaningChecklist)
class CleaningChecklistAdmin(ModelAdmin):
  list_display = ('title',)


@admin.register(Maintenance)
class MaintenanceAdmin(ModelAdmin):
  list_display = (
      'title', 'rental', 'created_at', 'accepted_by', 'offered_start_time',
      'completed_at')


class ManualPaymentForm(forms.ModelForm):
  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    # If we get around to turning worker into a foreign key to
    # IndependentWorker then this can go away.
    self.fields['worker'].queryset = IndependentWorker.objects.all()

  class Meta:
    fields = (
        'subject', 'message', 'worker', 'work_co', 'building', 'amount',
        'manual_paypal_transaction_id', 'manual_paypal_transaction_when',
        'work_completed', 'on_hold_reason', 'notes', 'receipt_photo_url')
    model = ManualPayment


class PaymentAdmin(ModelAdmin):
  def payout_status(self, instance):
    if instance.paypal_payout:
      return instance.paypal_payout.status()


@admin.register(ManualPayment)
class ManualPaymentAdmin(PaymentAdmin):
  form = ManualPaymentForm

  list_display = (
      'subject', 'message', 'worker', 'work_co', 'amount', 'building',
      'on_hold_reason', 'payout_status')
  list_select_related = ('paypal_payout', 'worker', 'work_co')


class WorkPaymentForm(forms.ModelForm):
  class Meta:
    fields = (
        'hours_override', 'on_hold_reason', 'notes',
        'manual_paypal_transaction_id', 'manual_paypal_transaction_when')
    model = WorkPayment


@admin.register(WorkPayment)
class WorkPaymentAdmin(PaymentAdmin):
  form = WorkPaymentForm

  def describe_work(self, instance):
    return instance.work.get_child_class_instance().get_readable_work_title()
  describe_work.short_description = 'work'

  def worker(self, instance):
    return instance.work.accepted_by.name

  def amount(self, instance):
    return currency(instance.get_total_amount())

  list_display = (
      'describe_work', 'worker', 'amount', 'hours_override', 'on_hold_reason',
      'payout_status')
  list_select_related = ('work', 'work__accepted_by')


class LineItemInlineFormset(forms.models.BaseInlineFormSet):
  def clean(self, *args, **kwargs):
    for form in self.forms:
      if form.cleaned_data:
        if len(form.cleaned_data.get('description', '')) < 3:
          raise ValidationError(
              'Line item descriptions must be at least 3 characters long. If '
              'you\'re trying to delete a line item, use the delete '
              'checkboxes to the right.')
    return super().clean(*args, **kwargs)


class LineItemInline(admin.TabularInline):
  model = LineItem
  formset = LineItemInlineFormset


class OneOffChangeList(ChangeList):
  def url_for_result(self, result):
    return result.url()


@admin.register(OneOff)
class OneOffAdmin(ModelAdmin):
  class Media:
    js = (
        '//code.jquery.com/jquery-1.12.4.js',
        'admin_helptext_hack.js',
        'one_off.js')

  def get_changelist(self, request, **kwargs):
    return OneOffChangeList

  def save_formset(self, request, form, formset, change):
    """ I want the related objects to all get saved first so that the OneOff
    save() function has a chance to set offered_to. Otherwise the Django admin
    just overwrites the work that set_offered_to does.
    https://stackoverflow.com/questions/14858559/save-the-related-objects-before-the-actual-object-being-edited-on-django-admin """  # noqa: E501
    formset.save()  # this will save the offered_to specified in the form
    # This will save the OneOff instance, which triggers the post_save which
    # sets the offered_to based on WorkType (if specified).
    form.instance.save()

  def get_status_transition(self, one_off):
    if one_off.status() == CREATED:
      if not one_off.offered_to.count():
        return '{} doesn\'t have any service providers.'.format(
            one_off.properly_rental.rental.nickname)
      else:
        # See static/one_off.js for how this is wired up.
        return format_html((
            '<div class="create_wrapper" data-id="{}" data-readonly="{}">'
            '<button type="button">Create</button>'
            '</div>'), one_off.pk, one_off.get_readonly_admin_url())
    return one_off.status()
  get_status_transition.short_description = 'Status'

  def get_work_payment(self, one_off):
    if one_off.workpayment_or_none:
      return format_html(
          '<a href="{}">{}</a>',
          one_off.workpayment.admin_url(),
          one_off.workpayment.invoice_number())
  get_work_payment.short_description = 'Payment'

  list_display = (
      'title', 'properly_rental', 'created_at', 'offered_start_time',
      'get_status_transition', 'get_work_payment', 'accepted_by')
  list_select_related = ('workpayment', 'properly_rental', 'accepted_by')

  # static/one_off.js makes it so you can only enter an existing checklist or
  # line items, but not both.
  fieldsets = (
      (None, {'fields': ('title', 'message', 'properly_rental')}),
      ('Who', {'fields': ('work_type', 'offered_to')}),
      ('When', {'fields': (
          'fixed_or_flexible', 'offered_start_time', 'end_time',
          'expected_duration')}),
      ('Existing checklist', {'fields': ('existing_checklist_url',)}))

  inlines = [LineItemInline]


@admin.register(RepeatWork)
class RepeatWorkAdmin(ModelAdmin):
  def title(self, instance):
    return instance.repeat_config.title

  def rental(self, instance):
    return instance.repeat_config.properly_rental.rental.nickname

  def accepted_by(self, instance):
    return instance.accepted_by and instance.accepted_by.name

  list_display = (
      'title', 'rental', 'offered_start_time', 'accepted_by', 'status')
  list_select_related = (
      'repeat_config', 'repeat_config__properly_rental',
      'repeat_config__properly_rental__rental', 'accepted_by')


@admin.register(RepeatConfig)
class RepeatConfigAdmin(ModelAdmin):
  def last(self, instance):
    latest = instance.get_last_complete_ticket()
    if latest:
      return latest.completed_at

  def explain(self, instance):
    return instance.explain_why_cant_create_ticket() or (
        'Yes, this should create a ticket today!')
  explain.short_description = 'Create ticket?'

  def get_queryset(self, request):
    """ Django doesn't have list_prefetch_related yet """
    qs = super().get_queryset(request)
    return qs.prefetch_related('repeatwork_set')

  list_display = (
      'title', 'properly_rental', 'work_type', 'last', 'explain')
  list_select_related = (
      'properly_rental', 'properly_rental__rental', 'work_type')


@admin.register(WorkCoWorker)
class WorkCoWorkerAdmin(ModelAdmin):
  list_display = (
      'name', 'phone', 'email', 'work_co', 'active',
      'active_by_cleaning_company', 'internal_notes')
  list_filter = ('work_co',)


@admin.register(IndependentWorker)
class IndependentWorkerAdmin(ModelAdmin):
  work_types_created = False

  def get_buildings(self, instance):
    all_buildings = instance.buildings.all()
    return ', '.join(
        [building.get_nickname() for building in all_buildings])
  get_buildings.short_description = 'buildings'

  def get_work_types(self, instance):
    if not self.work_types_created:
      # We need to do this somewhere. Don't do it in __init__ because then it
      # might run during tests before the table is installed causing weird
      # errors.
      WorkType.objects.create_work_types()
      self.work_types_created = True
    return ', '.join(
        [work_type.name for work_type in instance.work_types.all()])
  get_work_types.short_description = 'work types'

  def cleaning_score(self, instance):
    return mark_safe('<a href="{}">Cleaning score</a>'.format(
        instance.cleaning_score_url()))

  list_display = (
      'name', 'get_work_types', 'phone', 'email', 'hour_rate', 'worker_id',
      'get_buildings', 'hour_min', 'cleaning_score')
  exclude = ('phone_numbers_only',)


class ProperlyRentalForm(forms.ModelForm):
  """ The point of this form is to exclude source_property_id from the admin.
  """
  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    # Every rental that's set up in properly costs money, and anyway all forms
    # of work happen on atom rentals, so it doesn't really make sense to
    # configure a combo rental in properly.
    self.fields['rental'].queryset = Rental.objects.filter(
        combo_unit_description='')

  class Meta:
    fields = (
        'rental', 'properly_property_id', 'clean_co',
        'cleaning_flat_rate')
    model = ProperlyRental


@admin.register(WorkType)
class WorkTypeAdmin(ModelAdmin):
  list_display = ('name',)


class ProperlyRentalFormSet(BaseModelFormSet):
  def clean(self):
    for instance in self.cleaned_data:
      if bool(instance['clean_co']) and not bool(
          instance['cleaning_flat_rate']):
        raise forms.ValidationError(
            instance['id'].rental.nickname + (
                ': if you specify a cleaning work_co, you must also specify '
                'a cleaning flat rate.'))


@admin.register(ProperlyRental)
class ProperlyRentalAdmin(ModelAdmin):
  form = ProperlyRentalForm

  def rental_nickname(self, instance):
    return instance.rental.nickname

  def get_changelist_formset(self, request, **kwargs):
    kwargs['formset'] = ProperlyRentalFormSet
    return super().get_changelist_formset(request, **kwargs)

  list_display = (
      'rental', 'rental_nickname', 'clean_co', 'cleaning_flat_rate',
      'properly_property_id')
  list_editable = ('clean_co', 'cleaning_flat_rate')
  list_select_related = ('rental',)
  list_filter = ('clean_co', 'rental__building')


@admin.register(CleaningConfig)
class CleaningConfigAdmin(ModelAdmin):
  def rental(self, instance):
    return instance.properly_rental.rental.nickname

  def bedrooms(self, instance):
    return instance.properly_rental.rental.bedrooms

  def bathrooms(self, instance):
    return instance.properly_rental.rental.bathrooms

  list_display = (
      'rental', 'bedrooms', 'bathrooms', 'keys_notes',
      'cleaning_checklist', 'properly_checklist_id')
  list_select_related = ('properly_rental__rental',)


@admin.register(Cleaning)
class CleaningAdmin(ModelAdmin):
  def get_rental(self, instance):
    if instance.reservation:
      return instance.reservation.rental.nickname
  get_rental.short_description = 'Where'

  def get_service_provider(self, instance):
    if instance.accepted_by:
      return instance.accepted_by.name
  get_service_provider.short_description = 'Accepted by'

  list_display = (
      'get_rental', 'get_service_provider', 'offered_start_time', 'created_at',
      'status')
  list_select_related = ('reservation__rental', 'accepted_by')
  list_filter = ('reservation__rental', 'accepted_by')


@admin.register(Inspection)
class InspectionAdmin(ModelAdmin):
  pass


@admin.register(SubjectLine)
class SubjectLineAdmin(ModelAdmin):
  list_display = ('reason', 'subject')


@admin.register(Message)
class MessageAdmin(ModelAdmin):
  def job(self, instance):
    if instance.work:
      return format_html(
          '<a href="{}">{}</a>',
          reverse('child_class_details', kwargs={'pk': instance.work.pk}),
          instance.work)
  list_display = (
      'when', 'job', 'to', 'reason', 'kind', 'subject', 'content',
      'delivery_error')
  list_select_related = ('work',)
  list_filter = ('reason',)


@admin.register(RawEvent)
class RawEventAdmin(ModelAdmin):
  def job(self, instance):
    if instance.work:
      work = instance.work.get_child_class_instance()
      return mark_safe((
          '<a href="{}">{} {} {}</a>').format(
              work.url(), work._meta.model_name,
              work.get_rental().nickname, work.offered_start_time.date()))

  list_display = (
      'event_name', 'created_at', 'handled_at', 'job', 'error')
  list_filter = ('event_name',)
  list_select_related = (
      'work',
      'work__oneoff',
      'work__oneoff__properly_rental',
      'work__oneoff__properly_rental__rental',
      'work__cleaning',
      'work__cleaning__rental')


@admin.register(WorkCo)
class WorkCoAdmin(ModelAdmin):
  list_display = ('name', 'owner', 'alerts_email', 'services_tax_rate')
