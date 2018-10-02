from django.contrib import admin

from rentals.models import Rental, Building


class RentalAdmin(admin.ModelAdmin):
  pass


class BuildingAdmin(admin.ModelAdmin):
  pass


admin.site.register(Rental, RentalAdmin)
admin.site.register(Building, BuildingAdmin)
