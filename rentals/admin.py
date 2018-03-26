from django.contrib import admin
from rentals.models import Rental, Owner


class RentalAdmin(admin.ModelAdmin):
  list_display = ('airbnb_address_scrape', 'owner')


class OwnerAdmin(admin.ModelAdmin):
  list_display = ('name', 'email', 'payout_rule')


admin.site.register(Rental, RentalAdmin)
admin.site.register(Owner, OwnerAdmin)
