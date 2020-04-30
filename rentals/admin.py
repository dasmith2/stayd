import re

from django.contrib import admin
from django.shortcuts import redirect, reverse

from rentals.forms import RentalForm, BuildingForm
from rentals.models import Rental, Building, MonthlyExpense
from util.admin import ModelAdmin


def clean_up_dupe_rentals(modeladmin, request, queryset):
  ids = ','.join([str(rental.pk) for rental in queryset])
  return redirect(reverse('clean_up_dupe_rentals') + '?ids={}'.format(ids))


clean_up_dupe_rentals.short_description = 'Clean up duplicate rentals'


@admin.register(Rental)
class RentalAdmin(ModelAdmin):
  form = RentalForm

  def building_owner(self, instance):
    return instance.building.owner

  def formfield_for_manytomany(self, db_field, request, **kwargs):
    if db_field.name == 'is_combo_of':
      rental_id_finder = re.compile(r'/admin/rentals/rental/(\d+)/change/')
      match = rental_id_finder.match(request.path)
      if match:
        # It won't match on /admin/rentals/rental/add/
        rental_id = int(match.groups()[0])
        rental = Rental.objects.get(pk=rental_id)
        kwargs['queryset'] = Rental.objects.exclude(pk=rental_id).filter(
            building=rental.building, combo_unit_description='')
    return super().formfield_for_manytomany(db_field, request, **kwargs)

  list_display = (
      'building', 'apartment', 'building_owner', 'nickname', 'is_active',
      'combo_unit_description', 'reports_start_date')
  actions = [clean_up_dupe_rentals]


@admin.register(Building)
class BuildingAdmin(ModelAdmin):
  form = BuildingForm

  list_display = (
      'address', 'nickname', 'city', 'owner', 'is_active',
      'alerts_email', 'sms_staff_from')


@admin.register(MonthlyExpense)
class MonthlyExpenseAdmin(ModelAdmin):
  list_display = ('rental', 'start_date', 'monthly_amount', 'kind')
  list_filter = ('rental',)
