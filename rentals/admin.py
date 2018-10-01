from django.contrib import admin

from rentals.models import Rental, Building


class RentalAdmin(admin.ModelAdmin):
  list_display = ('full_address', 'owner')


admin.site.register(Rental, RentalAdmin)


class BuildingAdmin(admin.ModelAdmin):
  list_display = ('full_address', 'owner')


admin.site.register(Building, BuildingAdmin)
