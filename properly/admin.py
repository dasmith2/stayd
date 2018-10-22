from django.contrib import admin

from properly.models import Cleaner


@admin.register(Cleaner)
class CleanerAdmin(admin.ModelAdmin):
  def get_buildings(self, instance):
    return ', '.join([building.nickname for building in instance.buildings])

  list_display = ('name', 'phone', 'email', 'hourly_rate')
