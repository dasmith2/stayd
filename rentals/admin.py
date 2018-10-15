from django import forms
from django.contrib import admin

from rentals.models import Rental, Building


class RentalForm(forms.ModelForm):
  class Meta:
    fields = ('building',)
    model = Rental


class RentalAdmin(admin.ModelAdmin):
  form = RentalForm

  list_display = (
      'building', 'apartment', 'nickname', 'is_active')


class BuildingForm(forms.ModelForm):
  class Meta:
    fields = ('owner', 'nickname', 'is_active')
    model = Building


class BuildingAdmin(admin.ModelAdmin):
  form = BuildingForm

  list_display = ('address', 'nickname', 'owner', 'is_active')


admin.site.register(Rental, RentalAdmin)
admin.site.register(Building, BuildingAdmin)
