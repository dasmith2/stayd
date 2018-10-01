from django.contrib import admin

from rentals.models import Rental, Building


class RentalAdmin(admin.ModelAdmin):
  list_display = ('full_address', 'owner')


class BuildingAdmin(admin.ModelAdmin):
  pass


admin.site.register(Rental, RentalAdmin)
admin.site.register(Building, BuildingAdmin)
