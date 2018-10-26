from django import forms
from django.contrib import admin

from rentals.models import Rental, Building


class RentalForm(forms.ModelForm):
  class Meta:
    fields = ('building', 'reports_start_date',)
    model = Rental


@admin.register(Rental)
class RentalAdmin(admin.ModelAdmin):
  form = RentalForm

  def building_owner(self, instance):
    return instance.building.owner

  list_display = (
      'building', 'building_owner', 'apartment', 'nickname', 'is_active',
      'reports_start_date')


class BuildingForm(forms.ModelForm):
  class Meta:
    fields = ('owner', 'nickname', 'is_active', 'alerts_email')
    model = Building


@admin.register(Building)
class BuildingAdmin(admin.ModelAdmin):
  form = BuildingForm

  list_display = ('address', 'nickname', 'owner', 'is_active', 'alerts_email')
