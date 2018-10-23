from django.contrib import admin

from properly.models import Cleaner, Checklist, RentalChecklist


@admin.register(Cleaner)
class CleanerAdmin(admin.ModelAdmin):
  def get_buildings(self, instance):
    return ', '.join([building.nickname for building in instance.buildings])

  list_display = ('name', 'phone', 'email', 'hourly_rate')


@admin.register(Checklist)
class ChecklistAdmin(admin.ModelAdmin):
  list_display = ('properly_id', 'name')


@admin.register(RentalChecklist)
class RentalChecklistAdmin(admin.ModelAdmin):
  list_display = (
      'rental', 'properly_rental_id', 'checklist', 'cleaning_duration')
