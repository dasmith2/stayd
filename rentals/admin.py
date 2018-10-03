from django.contrib import admin

from rentals.models import Rental, Building


class RentalAdmin(admin.ModelAdmin):
  list_display = (
      'building', 'full_address', 'nickname', 'is_active')


class BuildingAdmin(admin.ModelAdmin):
  list_display = ('address', 'nickname', 'owner', 'is_active')


admin.site.register(Rental, RentalAdmin)
admin.site.register(Building, BuildingAdmin)
