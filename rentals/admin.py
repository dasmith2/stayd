from django.contrib import admin
from rentals.models import Rental


class RentalAdmin(admin.ModelAdmin):
  list_display = (
      'airbnb_address_scrape', 'time_zone', 'currency', 'accommodates',
      'bathrooms', 'bedrooms', 'property_type', 'room_type')


admin.site.register(Rental, RentalAdmin)
