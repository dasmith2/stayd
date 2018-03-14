from django.contrib import admin
from rentals.models import Rental


class RentalAdmin(admin.ModelAdmin):
  list_display = RentalAdmin._meta.get_all_field_names()


admin.site.register(Rental, RentalAdmin)
